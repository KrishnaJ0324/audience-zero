"""Story Tree — free-form time-travel branching over a trunk Version's beats.

A story tree is scoped to one trunk ``Version`` (``root_version_id``); the
original ingested script is never edited. Nodes are immutable once created —
branching is always a new row with a new id and ``parent_node_id`` set, never
an edit to an existing node. That is what gives "never mutates history" for
free, with no special-case logic anywhere else.

Each node owns a full, independent copy of character state (memory, emotional
state, relationships) — copy-on-write, enforced by the heuristics/provider
layer never mutating an input dict in place. Consistency checking is a
separate LLM-as-judge pass that can only attach warnings; it never blocks or
retries node creation.
"""
from __future__ import annotations

import uuid

from ..contracts import Beat, CharacterState, ConsistencyIssue, StoryAdvance, StoryNode, Version
from ..providers.factory import Providers
from .session_store import SessionStore


def _sid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class StoryTreeService:
    def __init__(self, providers: Providers, store: SessionStore, context_window: int = 3) -> None:
        self.p = providers
        self.store = store
        self.k = max(1, context_window)

    # ------------------------------------------------------------------ #
    # Seeding — turn a trunk Version's existing beats into a linear spine
    # ------------------------------------------------------------------ #
    async def seed_spine(self, root: Version) -> list[StoryNode]:
        existing = await self.store.list_nodes_for_version(root.id)
        if existing:
            return existing  # idempotent: don't re-seed / re-spend calls

        nodes: list[StoryNode] = []
        parent_id: str | None = None
        states: dict[str, CharacterState] = {}
        for beat in root.beats:
            states = await self.p.llm.extract_character_state(states, beat.text)
            node = StoryNode(
                id=_sid("node"),
                root_version_id=root.id,
                episode_id=root.episode_id,
                project_id=root.project_id,
                parent_node_id=parent_id,
                beat_index=beat.index,
                text=beat.text,
                summary=beat.summary,
                character_states=states,
                label=f"beat {beat.index + 1}",
            )
            await self.store.save_node(node)
            nodes.append(node)
            parent_id = node.id
        return nodes

    # ------------------------------------------------------------------ #
    # Branching — the free-form "what happens next" action
    # ------------------------------------------------------------------ #
    async def branch(self, parent_node_id: str, instruction: str) -> StoryNode:
        parent = await self.store.get_node(parent_node_id)
        if not parent:
            raise ValueError("story node not found")

        chain = await self._ancestor_chain(parent)  # root .. parent, inclusive
        context_text, ancestor_summaries = self._assemble_context(chain)
        advance, issues = await self._advance(
            parent.character_states, context_text, ancestor_summaries + [parent.summary], instruction)

        node = StoryNode(
            id=_sid("node"),
            root_version_id=parent.root_version_id,
            episode_id=parent.episode_id,
            project_id=parent.project_id,
            parent_node_id=parent.id,
            beat_index=parent.beat_index + 1,
            prompt=instruction,
            text=advance.text,
            summary=advance.summary or instruction[:90],
            character_states=advance.character_states,
            consistency_issues=issues,
            label=f"branch of {parent.id[-6:]}",
        )
        await self.store.save_node(node)
        return node

    # ------------------------------------------------------------------ #
    # Cross-episode continuation — same generation engine as branch(), but
    # the result becomes the ROOT of a brand-new tree in a different
    # Version/Episode. This is the mechanism that carries a universe's
    # memory/relationships across an episode boundary.
    # ------------------------------------------------------------------ #
    async def continue_into(
        self,
        source_node: StoryNode,
        target_version_id: str,
        target_episode_id: str,
        target_project_id: str,
        instruction: str,
    ) -> StoryNode:
        chain = await self._ancestor_chain(source_node)
        context_text, ancestor_summaries = self._assemble_context(chain)
        advance, issues = await self._advance(
            source_node.character_states, context_text,
            ancestor_summaries + [source_node.summary], instruction)

        node = StoryNode(
            id=_sid("node"),
            root_version_id=target_version_id,
            episode_id=target_episode_id,
            project_id=target_project_id,
            parent_node_id=None,  # root of a NEW tree — not appended to the source's
            beat_index=0,
            prompt=instruction,
            text=advance.text,
            summary=advance.summary or instruction[:90],
            character_states=advance.character_states,
            consistency_issues=issues,
            label=f"continued from {source_node.id[-6:]}",
        )
        await self.store.save_node(node)
        return node

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    async def list_tree(self, root_version_id: str) -> list[StoryNode]:
        return await self.store.list_nodes_for_version(root_version_id)

    async def get_node(self, node_id: str) -> StoryNode | None:
        return await self.store.get_node(node_id)

    # ------------------------------------------------------------------ #
    # Materialize — hand a branch off to the EXISTING analyze/panel pipeline
    # ------------------------------------------------------------------ #
    async def materialize_to_version(self, node_id: str) -> Version:
        """Walk the node's ancestor chain into a bare (unsaved) Version so the
        existing /versions/{id}/analyze + persona-panel pipeline can run on it
        completely unchanged. Caller is responsible for persisting it."""
        node = await self.store.get_node(node_id)
        if not node:
            raise ValueError("story node not found")
        chain = await self._ancestor_chain(node)  # root .. node

        beats = [
            Beat(index=i, start_s=0.0, end_s=0.0, summary=n.summary or f"beat {i + 1}", text=n.text)
            for i, n in enumerate(chain)
        ]
        transcript = "\n\n".join(b.text for b in beats)
        total = max(len(transcript.split()) / 2.4, 60.0)  # same pacing heuristic as segment()
        per = total / max(len(beats), 1)
        for i, b in enumerate(beats):
            b.start_s, b.end_s = round(i * per, 2), round((i + 1) * per, 2)

        root = await self.store.get_version(node.root_version_id)
        title = f"{root.title if root else 'Story'} — branch"
        return Version(
            id=_sid("ver"),
            title=title,
            source_type="script",
            transcript=transcript,
            duration_s=beats[-1].end_s if beats else None,
            beats=beats,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    async def _advance(
        self,
        prior_states: dict[str, CharacterState],
        context_text: str,
        ancestor_summaries: list[str],
        instruction: str,
    ) -> tuple[StoryAdvance, list[ConsistencyIssue]]:
        advance = await self.p.llm.advance_story(prior_states, context_text, instruction)
        try:
            issues = await self.p.llm.check_consistency(
                prior_states, ancestor_summaries, advance.text, advance.character_states,
            )
        except Exception:  # noqa: BLE001 — consistency check must never block creation
            issues = []
        return advance, issues

    async def _ancestor_chain(self, node: StoryNode) -> list[StoryNode]:
        chain = [node]
        cur = node
        while cur.parent_node_id:
            nxt = await self.store.get_node(cur.parent_node_id)
            if not nxt:
                break
            chain.append(nxt)
            cur = nxt
        return list(reversed(chain))

    def _assemble_context(self, chain: list[StoryNode]) -> tuple[str, list[str]]:
        """Keep prompt size flat regardless of tree depth: full text of the
        last ``k`` ancestors, one-line summaries for everything older. The
        immediate parent's character_states (passed separately) carry the
        compressed long-range memory."""
        recent = chain[-self.k:]
        older = chain[:-self.k] if len(chain) > self.k else []
        context_text = "\n\n".join(f"[{n.label or n.id}] {n.text}" for n in recent)
        return context_text, [n.summary for n in older if n.summary]
