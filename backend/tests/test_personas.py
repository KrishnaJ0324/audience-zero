"""Custom persona roster: created personas auto-join the panel and flow through
the whole pipeline (reports, verdict, manifest)."""
from __future__ import annotations

import asyncio

from app.config import get_settings
from app.pipeline import Pipeline


def _pipeline() -> Pipeline:
    s = get_settings()
    s.provider = "mock"
    s.reveal_delay_s = 0.0
    return Pipeline(settings=s)


def test_custom_persona_joins_roster_and_run():
    async def _go():
        p = _pipeline()
        await p.init()
        base = len(await p.roster())
        cp = await p.create_persona(
            "Zoya", "Gen-Z speedrunner",
            "You are Zoya, a Gen-Z listener who loves fast pacing and hates recap.")
        assert cp.custom and cp.color and cp.voice_id
        roster = await p.roster()
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
        assert len(await p.roster()) == base

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
