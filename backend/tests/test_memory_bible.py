"""Story bible (memory.md) tests: manual generation at the root, bundled
generation on cross-episode continuation (only when the parent opted in),
and never-mutates-the-parent's-spec continuity.
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


def _vid() -> str:
    return f"ver_test_{uuid.uuid4().hex[:10]}"


async def _root_version(p: Pipeline):
    project = await p.create_project("Memory Test")
    episode = await p.create_episode(project.id, "Episode 1", sequence=1)
    beats = [
        Beat(index=0, start_s=0.0, end_s=10.0, summary="Kael vows to protect Dev",
             text="KAEL: I will always protect DEV, no matter the cost."),
        Beat(index=1, start_s=10.0, end_s=20.0, summary="Dev trusts Kael",
             text="DEV: I trust you completely, Kael."),
    ]
    version = Version(
        id=_vid(), title="Episode 1", source_type="script",
        transcript="\n\n".join(b.text for b in beats), beats=beats,
        project_id=project.id, episode_id=episode.id, label="v1",
    )
    await p.store.save_version(version)
    version = await p.assign_universe(version.id, new_universe_name="Universe A")
    return project, episode, version


def test_root_memory_generation_populates_spec_and_markdown():
    async def _go():
        p = _pipeline()
        await p.init()
        _, _, version = await _root_version(p)
        return await p.generate_memory_for_version(version.id)

    version = asyncio.run(_go())
    assert version.memory_spec is not None
    assert version.memory_spec.theme
    names = {c.name for c in version.memory_spec.characters}
    assert "KAEL" in names
    assert "Story Bible" in version.memory_md
    assert "KAEL" in version.memory_md


def test_continue_without_root_memory_does_not_auto_generate_child_bible():
    async def _go():
        p = _pipeline()
        await p.init()
        _, _, version = await _root_version(p)  # no memory generated on root
        result = await p.continue_universe(version.id, instruction="Dev leaves to warn the others.")
        return result["version"]

    target = asyncio.run(_go())
    assert target.memory_spec is None
    assert target.memory_md == ""


def test_continue_bundles_child_memory_when_parent_opted_in():
    async def _go():
        p = _pipeline()
        await p.init()
        _, _, version = await _root_version(p)
        root = await p.generate_memory_for_version(version.id)
        result = await p.continue_universe(root.id, instruction="Kael and Dev regroup at the old bridge.")
        return root, result["version"]

    root, target = asyncio.run(_go())
    assert target.memory_spec is not None
    assert target.memory_md != ""
    # theme carries forward from the parent bible rather than being re-derived
    assert target.memory_spec.theme == root.memory_spec.theme
    # parent's spec itself is untouched (fresh-per-version, never mutated)
    assert root.memory_spec.theme and root.memory_md


def test_explicit_generate_on_child_inherits_parent_characters():
    async def _go():
        p = _pipeline()
        await p.init()
        _, _, version = await _root_version(p)
        root = await p.generate_memory_for_version(version.id)

        child_id = _vid()
        child = Version(
            id=child_id, title="Episode 2", source_type="script",
            transcript="RIAA: A new voice enters the story.",
            beats=[Beat(index=0, start_s=0.0, end_s=8.0, summary="Riaa arrives",
                        text="RIAA: A new voice enters the story.")],
            project_id=root.project_id, episode_id=root.episode_id,
            label="v2", parent_version_id=root.id, universe_id=root.universe_id,
        )
        await p.store.save_version(child)
        return root, await p.generate_memory_for_version(child_id)

    root, child = asyncio.run(_go())
    parent_names = {c.name for c in root.memory_spec.characters}
    child_names = {c.name for c in child.memory_spec.characters}
    assert parent_names <= child_names  # carried forward, not dropped
    assert "RIAA" in child_names  # plus the newly introduced character
