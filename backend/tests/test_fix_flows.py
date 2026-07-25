"""Fix-loop integration tests: the weakest-beat fix reduces drop, and the
strengthen-ending fix never lowers Binge Probability (§2.10)."""
from __future__ import annotations

import asyncio

from app.config import get_settings
from app.pipeline import Pipeline


def _pipeline() -> Pipeline:
    s = get_settings()
    s.provider = "mock"
    s.reveal_delay_s = 0.0
    return Pipeline(settings=s)


def _fix_and_rerun(script: str, target: str):
    async def _go():
        p = _pipeline()
        await p.init()
        text = (p.s.scripts_dir / script).read_text(encoding="utf-8")
        ep = await p.ingest_script(script, text)
        rid = p.new_run_id()
        await p.run_panel(ep, rid, speak_verdicts=0)
        await p.revise_run(rid, target=target)
        _, cmp = await p.rerun_with_fix(rid)
        return cmp

    return asyncio.run(_go())


def test_weakest_fix_reduces_drop_at_the_weak_beat():
    cmp = _fix_and_rerun("demo_episode.txt", "weakest")
    assert cmp.target == "weakest"
    assert cmp.after_drop_pct < cmp.before_drop_pct
    assert cmp.lift_pct > 0


def test_strengthen_ending_never_lowers_binge_probability():
    # weak-ending script: a large positive lift
    cmp = _fix_and_rerun("calib_romance.txt", "ending")
    assert cmp.target == "ending"
    assert cmp.binge_lift_pct > 0
    # already-strong ending: must still be non-negative, never a regression
    cmp2 = _fix_and_rerun("demo_episode.txt", "ending")
    assert cmp2.binge_lift_pct >= 0
    assert cmp2.beat_index == cmp2.after_curve.__len__() - 1  # the final beat
