"""Custom persona roster: created personas auto-join the panel and flow through
the whole pipeline (reports, verdict, manifest)."""
from __future__ import annotations

import asyncio

from app.config import get_settings
from app.pipeline import _DEFAULT_PROJECT_ID, Pipeline

PROJ = _DEFAULT_PROJECT_ID


def _pipeline() -> Pipeline:
    s = get_settings()
    s.provider = "mock"
    s.reveal_delay_s = 0.0
    return Pipeline(settings=s)


def test_custom_persona_joins_roster_and_run():
    async def _go():
        p = _pipeline()
        await p.init()
        base = len(await p.roster(PROJ))
        cp = await p.create_persona(
            "Zoya", "Gen-Z speedrunner",
            "You are Zoya, a Gen-Z listener who loves fast pacing and hates recap.")
        assert cp.custom and cp.color and cp.voice_id
        roster = await p.roster(PROJ)
        assert len(roster) == base + 1
        assert cp.id in [x.id for x in roster]

        text = (p.s.scripts_dir / "demo_episode.txt").read_text(encoding="utf-8")
        v = await p.ingest_script("Ep", text)
        run = await p.run_panel(v, p.new_run_id(), speak_verdicts=0)
        assert cp.id in [r.persona_id for r in run.reports]
        assert any(s.persona_id == cp.id for s in run.verdict.per_persona_summary)
        assert cp.id in run.run_manifest.persona_ids
        assert len(run.verdict.aggregate_curve) == len(v.beats)

        await p.delete_persona(cp.id)
        assert len(await p.roster(PROJ)) == base

    asyncio.run(_go())


def test_persona_enablement_is_per_project():
    async def _go():
        p = _pipeline()
        await p.init()
        a = await p.create_project("Project A")
        b = await p.create_project("Project B")
        # disable arjun in A only
        await p.set_persona_enabled(a.id, "arjun", False)
        assert "arjun" not in [x.id for x in await p.roster(a.id)]
        assert "arjun" in [x.id for x in await p.roster(b.id)]  # B unaffected

        # analyzing an episode in A excludes arjun; in B it's present
        text = (p.s.scripts_dir / "demo_episode.txt").read_text(encoding="utf-8")
        va = await p.add_script_version("Ep", text, project_id=a.id,
                                        episode_id=(await p.create_episode(a.id, "Ep")).id)
        run_a = await p.run_panel(va, p.new_run_id(), speak_verdicts=0)
        assert "arjun" not in [r.persona_id for r in run_a.reports]

        vb = await p.add_script_version("Ep", text, project_id=b.id,
                                        episode_id=(await p.create_episode(b.id, "Ep")).id)
        run_b = await p.run_panel(vb, p.new_run_id(), speak_verdicts=0)
        assert "arjun" in [r.persona_id for r in run_b.reports]

    asyncio.run(_go())


def test_cannot_disable_the_last_persona_in_a_project():
    async def _go():
        p = _pipeline()
        await p.init()
        proj = await p.create_project("Solo")
        built = [x.id for x in await p.all_personas(proj.id)]
        for pid in built[:-1]:
            await p.set_persona_enabled(proj.id, pid, False)
        last = [x.id for x in await p.roster(proj.id)]
        assert len(last) == 1
        try:
            await p.set_persona_enabled(proj.id, last[0], False)
            assert False, "expected error disabling the last persona"
        except ValueError:
            pass
    asyncio.run(_go())


def test_persona_chat_returns_draft():
    async def _go():
        p = _pipeline()
        await p.init()
        r = await p.chat_persona([{"role": "user", "content": "A commuter named Sam who bails on slow openings"}])
        assert "reply" in r and "draft" in r
        assert r["draft"]["system_prompt"]
        assert r["draft"]["ready"] is True
    asyncio.run(_go())


def test_create_persona_validates():
    async def _go():
        p = _pipeline()
        await p.init()
        try:
            await p.create_persona("", "x", "prompt")
            assert False, "expected error on empty name"
        except ValueError:
            pass
        try:
            await p.create_persona("Name", "x", "")
            assert False, "expected error on empty prompt"
        except ValueError:
            pass
    asyncio.run(_go())
