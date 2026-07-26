"""Story tree (time-travel branching) integration tests.

Covers: cumulative character state on the seeded spine, copy-on-write
independence between sibling branches, non-blocking consistency warnings,
and the materialize seam into the EXISTING analyze/persona-panel pipeline.
"""
from __future__ import annotations

import asyncio
import uuid

from app.config import get_settings
from app.contracts import Beat, Version
from app.pipeline import Pipeline


def _pipeline() -> Pipeline:
    s = get_settings()
    s.provider = "mock"
    s.reveal_delay_s = 0.0
    return Pipeline(settings=s)


async def _seeded(p: Pipeline):
    """A small, hand-built trunk Version (bypasses the segmenter so beat text
    is fully controlled) + its seeded story-tree spine."""
    pid = await p._ensure_default_project()
    ep = await p.create_episode(pid, "Gate Story")
    beats = [
        Beat(index=0, start_s=0.0, end_s=10.0,
             summary="Maya vows to protect Dev",
             text="MAYA: I will always protect DEV, no matter what.\nNARRATOR: They shake hands."),
        Beat(index=1, start_s=10.0, end_s=20.0,
             summary="Dev thanks Maya",
             text="DEV: Thank you, Maya. I trust you completely."),
        Beat(index=2, start_s=20.0, end_s=30.0,
             summary="They move on before dawn",
             text="MAYA: We should keep moving before dawn."),
    ]
    version = Version(
        id=f"ver_test_{uuid.uuid4().hex[:10]}", title="Gate Story", source_type="script",
        transcript="\n\n".join(b.text for b in beats), beats=beats,
        project_id=pid, episode_id=ep.id, label="v1",
    )
    await p.store.save_version(version)
    nodes = await p.seed_story_tree(version.id)
    return version, nodes


def test_seed_spine_builds_cumulative_state():
    async def _go():
        p = _pipeline()
        await p.init()
        version, nodes = await _seeded(p)

        assert len(nodes) == len(version.beats)
        assert nodes[0].parent_node_id is None
        assert nodes[1].parent_node_id == nodes[0].id
        assert nodes[2].parent_node_id == nodes[1].id

        assert "MAYA" in nodes[-1].character_states
        assert nodes[-1].character_states["MAYA"].memory

        # idempotent: re-seeding returns the same node ids, no duplicate work
        again = await p.seed_story_tree(version.id)
        return nodes, again

    nodes, again = asyncio.run(_go())
    assert [n.id for n in again] == [n.id for n in nodes]


def test_branch_twice_creates_independent_siblings():
    async def _go():
        p = _pipeline()
        await p.init()
        _, nodes = await _seeded(p)
        parent = nodes[1]

        child_a = await p.branch_story_node(parent.id, "Dev confronts Maya about the missing map.")
        child_b = await p.branch_story_node(parent.id, "Maya slips away into the crowd without a word.")
        parent_after = await p.get_story_node(parent.id)
        return parent, child_a, child_b, parent_after

    parent, child_a, child_b, parent_after = asyncio.run(_go())
    assert child_a.parent_node_id == parent.id
    assert child_b.parent_node_id == parent.id
    assert child_a.id != child_b.id
    assert child_a.text != child_b.text
    # copy-on-write: branching must never mutate the parent node
    assert parent_after.text == parent.text
    assert parent_after.character_states == parent.character_states


def test_contradictory_instruction_flags_consistency():
    async def _go():
        p = _pipeline()
        await p.init()
        _, nodes = await _seeded(p)
        # nodes[0] establishes "MAYA ... protect DEV" — branch with the antonym
        return await p.branch_story_node(
            nodes[0].id, "Maya abandons Dev at the gate and runs alone.")

    node = asyncio.run(_go())
    assert len(node.consistency_issues) >= 1
    assert node.consistency_issues[0].character == "MAYA"


def test_materialize_feeds_existing_panel():
    async def _go():
        p = _pipeline()
        await p.init()
        root, nodes = await _seeded(p)
        child = await p.branch_story_node(nodes[1].id, "A stranger calls out from the dark.")
        version = await p.materialize_node_to_version(child.id)

        rid = p.new_run_id()
        run = await p.run_panel(version, rid, speak_verdicts=0)
        return root, version, run

    root, version, run = asyncio.run(_go())
    assert version.parent_version_id == root.id
    assert len(version.beats) == 3  # root beat0 -> beat1 -> the new branch node
    assert run.verdict is not None
