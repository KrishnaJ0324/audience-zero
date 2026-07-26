"""Cross-episode parallel universe tests: explicit universe tagging, episode
sequencing, and continuation (AI-seeded and no-op) across episode boundaries.
"""
from __future__ import annotations

import asyncio
import uuid

from app.config import get_settings
from app.contracts import Beat, Version
from app.pipeline import Pipeline


def _vid() -> str:
    return f"ver_test_{uuid.uuid4().hex[:10]}"


def _pipeline() -> Pipeline:
    s = get_settings()
    s.provider = "mock"
    s.reveal_delay_s = 0.0
    return Pipeline(settings=s)


async def _source_version(p: Pipeline):
    """A project with Episode 1 (sequence=1) and one Version tagged to a
    fresh universe, containing dialogue so character state is non-trivial."""
    project = await p.create_project("Serial Test")
    episode = await p.create_episode(project.id, "Episode 1", sequence=1)
    beats = [
        Beat(index=0, start_s=0.0, end_s=10.0, summary="Kael makes a vow",
             text="KAEL: I will guard this gate until the war ends."),
        Beat(index=1, start_s=10.0, end_s=20.0, summary="The siege begins",
             text="KAEL: They're here. Hold the line!"),
    ]
    version = Version(
        id=_vid(), title="Episode 1", source_type="script",
        transcript="\n\n".join(b.text for b in beats), beats=beats,
        project_id=project.id, episode_id=episode.id, label="v1",
    )
    await p.store.save_version(version)
    version = await p.assign_universe(version.id, new_universe_name="Universe A")
    return project, episode, version


def test_continue_with_no_instruction_creates_next_episode_only():
    async def _go():
        p = _pipeline()
        await p.init()
        _, episode, version = await _source_version(p)
        result = await p.continue_universe(version.id)
        return episode, result

    episode, result = asyncio.run(_go())
    assert result["version"] is None
    assert result["node"] is None
    assert result["episode"].sequence == episode.sequence + 1


def test_continue_with_instruction_carries_state_across_episode_boundary():
    async def _go():
        p = _pipeline()
        await p.init()
        _, _, version = await _source_version(p)
        result = await p.continue_universe(version.id, instruction="Kael abandons the gate and flees.")
        return version, result

    version, result = asyncio.run(_go())
    target_version, node = result["version"], result["node"]
    assert target_version is not None and node is not None
    assert target_version.parent_version_id == version.id
    assert target_version.universe_id == version.universe_id
    assert target_version.episode_id != version.episode_id
    assert node.root_version_id == target_version.id
    assert "KAEL" in node.character_states  # carried from the source's cumulative state


def test_continue_is_idempotent_per_universe_per_episode():
    async def _go():
        p = _pipeline()
        await p.init()
        _, _, version = await _source_version(p)
        first = await p.continue_universe(version.id, instruction="A stranger arrives at the gate.")
        second = await p.continue_universe(version.id, instruction="A completely different opening.")
        return first, second

    first, second = asyncio.run(_go())
    assert first["version"].id == second["version"].id
    assert first["episode"].id == second["episode"].id


def test_matrix_sorts_episodes_and_buckets_versions_by_universe():
    async def _go():
        p = _pipeline()
        await p.init()
        project, _, version = await _source_version(p)
        await p.continue_universe(version.id, instruction="They regroup at dawn.")
        return project, await p.get_project_matrix(project.id)

    project, matrix = asyncio.run(_go())
    seqs = [e.sequence for e in matrix["episodes"]]
    assert seqs == sorted(seqs)
    assert len(matrix["episodes"]) == 2
    assert len(matrix["universes"]) == 1
    assert len(matrix["versions"]) == 2
    assert {v.universe_id for v in matrix["versions"]} == {matrix["universes"][0].id}


def test_continuing_an_untagged_version_just_grows_the_main_line():
    """No universe was ever assigned; continuing it should still work and
    stay untagged — episodes grow linearly by default, no manual universe
    bookkeeping required."""
    async def _go():
        p = _pipeline()
        await p.init()
        project = await p.create_project("No Universe")
        episode = await p.create_episode(project.id, "Episode 1", sequence=1)
        version = Version(
            id=_vid(), title="Episode 1", source_type="script",
            transcript="text",
            beats=[Beat(index=0, start_s=0.0, end_s=5.0, summary="s", text="NARRATOR: hi.")],
            project_id=project.id, episode_id=episode.id, label="v1",
        )
        await p.store.save_version(version)
        return await p.continue_universe(version.id, instruction="The story continues quietly.")

    result = asyncio.run(_go())
    assert result["version"] is not None
    assert result["version"].universe_id == ""


def test_altering_an_episode_auto_branches_without_manual_assignment():
    """Adding a SECOND version to an episode that already has one is exactly
    'altering' it — should auto-mint a new universe and inherit the sibling's
    parent, with no explicit universe_id/parent_version_id from the caller."""
    async def _go():
        p = _pipeline()
        await p.init()
        project = await p.create_project("Auto Branch Test")
        episode = await p.create_episode(project.id, "Episode 1", sequence=1)
        v1 = await p.add_script_version(
            "Episode 1", "KAEL: I will guard this gate.",
            project_id=project.id, episode_id=episode.id, label="v1",
        )
        v2 = await p.add_script_version(
            "Episode 1", "KAEL: I abandon this gate.",
            project_id=project.id, episode_id=episode.id, label="v2",
        )
        return v1, v2

    v1, v2 = asyncio.run(_go())
    assert v1.universe_id == ""  # the original stays on the implicit main line
    assert v2.universe_id != ""  # the alteration auto-forked a real universe
    assert v2.parent_version_id == v1.parent_version_id  # true siblings, same parent


def test_new_episode_auto_chains_onto_the_projects_main_timeline():
    async def _go():
        p = _pipeline()
        await p.init()
        project = await p.create_project("Linear Growth Test")
        ep1 = await p.create_episode(project.id, "Episode 1", sequence=1)
        v1 = await p.add_script_version(
            "Episode 1", "KAEL: I will guard this gate.",
            project_id=project.id, episode_id=ep1.id, label="v1",
        )
        parent_id, universe_id = await p.default_continuation_for_new_episode(project.id)
        return v1, parent_id, universe_id

    v1, parent_id, universe_id = asyncio.run(_go())
    assert parent_id == v1.id
    assert universe_id is None  # v1 is untagged main — nothing to inherit


def test_fork_creates_a_brand_new_universe_child_of_the_source():
    async def _go():
        p = _pipeline()
        await p.init()
        _, _, version = await _source_version(p)  # already tagged "Universe A"
        result = await p.continue_universe(
            version.id, instruction="Kael quietly deserts in the night.",
            new_universe_name="Universe B",
        )
        return version, result

    version, result = asyncio.run(_go())
    child = result["version"]
    assert child is not None
    assert child.parent_version_id == version.id
    assert child.universe_id != version.universe_id  # a genuinely new universe


def test_forking_twice_from_one_parent_produces_two_distinct_children():
    """The actual 'one node, N edges falling into N different nodes' shape:
    the SAME source version forks into two separate universes/children."""
    async def _go():
        p = _pipeline()
        await p.init()
        _, _, version = await _source_version(p)
        child_1 = await p.continue_universe(
            version.id, instruction="Kael abandons the gate.", new_universe_name="Deserter")
        child_2 = await p.continue_universe(
            version.id, instruction="Kael seals the gate forever.", new_universe_name="Sealed")
        return version, child_1["version"], child_2["version"]

    parent, child_1, child_2 = asyncio.run(_go())
    assert child_1.id != child_2.id
    assert child_1.parent_version_id == parent.id
    assert child_2.parent_version_id == parent.id
    assert child_1.universe_id != child_2.universe_id
    assert child_1.episode_id == child_2.episode_id  # both land in the same next episode
