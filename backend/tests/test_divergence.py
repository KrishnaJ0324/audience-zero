"""Divergence acceptance test — the #1 product risk (§2.6).

Run the panel on three calibration scripts. PASS =
  * personas produce visibly divergent curves (not clones of each other),
  * they skip at different points,
  * the deliberately-boring-middle script's aggregate dips at its boring beats
    on every run (deterministic).
FAIL here means fix prompts/weights now, not at hour 20.
"""
from __future__ import annotations

import asyncio
import statistics

import pytest

from app.config import get_settings
from app.pipeline import Pipeline
from app.services import verdict_engine as ve


def _run(script_name: str):
    async def _go():
        s = get_settings()
        s.provider = "mock"
        s.reveal_delay_s = 0.0
        p = Pipeline(settings=s)
        await p.init()
        text = (s.scripts_dir / script_name).read_text(encoding="utf-8")
        ep = await p.ingest_script(script_name, text)
        run = await p.run_panel(ep, p.new_run_id(), speak_verdicts=0)
        return ep, run

    return asyncio.run(_go())


def _curves(run):
    return {r.persona_id: [s.engagement for s in r.scores] for r in run.reports}


def test_personas_are_not_clones():
    _, run = _run("demo_episode.txt")
    curves = _curves(run)
    assert len(curves) == 6
    # pairwise: at least one pair must differ substantially somewhere
    ids = list(curves)
    max_pair_diff = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            diff = max(abs(a - b) for a, b in zip(curves[ids[i]], curves[ids[j]]))
            max_pair_diff = max(max_pair_diff, diff)
    assert max_pair_diff >= 20, "persona curves are too similar — judgment isn't diverging"


def test_skip_points_diverge():
    _, run = _run("demo_episode.txt")
    skips = {r.persona_id: r.skip_at_beat for r in run.reports}
    distinct = set(skips.values())
    assert len(distinct) >= 2, f"all personas skip at the same point: {skips}"


def test_boring_middle_dips_in_the_middle():
    ep, run = _run("calib_boring_middle.txt")
    curve = run.verdict.aggregate_curve
    n = len(curve)
    first = curve[0]
    middle = statistics.mean(curve[1 : max(2, n - 1)])
    assert middle < first, "boring middle should score below the opening hook"
    # the weakest beat must be one of the recap-stuffed middle beats
    assert 1 <= run.verdict.weakest_beat <= n - 2


def test_thriller_rewards_kavya_more_than_romance_does():
    _, thriller = _run("calib_thriller.txt")
    _, romance = _run("calib_romance.txt")

    def mean_for(run, pid):
        r = next(r for r in run.reports if r.persona_id == pid)
        return statistics.mean(s.engagement for s in r.scores)

    # thriller purist should enjoy the thriller more than the pure romance
    assert mean_for(thriller, "kavya") > mean_for(romance, "kavya")
    # binge-romance listener should enjoy the romance more than the thriller
    assert mean_for(romance, "meera") > mean_for(thriller, "meera")


def test_determinism_across_runs():
    _, run_a = _run("demo_episode.txt")
    _, run_b = _run("demo_episode.txt")
    assert _curves(run_a) == _curves(run_b)
    assert run_a.verdict.headline == run_b.verdict.headline
