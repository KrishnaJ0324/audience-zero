"""Unit tests for the deterministic Verdict Engine (written first, per §2.3).

These lock the headline maths so it stays defensible under Q&A.
"""
from __future__ import annotations

from app.contracts import BeatScore, PersonaConfig, PersonaReport
from app.services import verdict_engine as ve


def _persona(pid: str, weight: float = 1.0) -> PersonaConfig:
    return PersonaConfig(
        id=pid, name=pid.title(), archetype="test", model="mock",
        system_prompt="", voice_id=f"{pid}_v", audience_weight=weight,
    )


def _report(pid: str, curve: list[int], skip: int | None = None) -> PersonaReport:
    return PersonaReport(
        persona_id=pid,
        scores=[BeatScore(beat_index=i, engagement=e) for i, e in enumerate(curve)],
        skip_at_beat=skip,
        verdict_text=f"{pid} speaks",
    )


def test_aggregate_curve_is_audience_weighted_mean():
    personas = [_persona("a", 1.0), _persona("b", 3.0)]
    reports = [_report("a", [100, 0]), _report("b", [0, 100])]
    curve = ve.aggregate_curve(reports, personas, 2)
    # beat0: (1*100 + 3*0)/4 = 25 ; beat1: (1*0 + 3*100)/4 = 75
    assert curve == [25.0, 75.0]


def test_retention_is_monotonically_non_increasing():
    churn = [0.0, 0.1, 0.2, 0.05]
    ret = ve.retention_from_churn(churn)
    assert ret[0] == 1.0
    assert all(ret[i] <= ret[i - 1] + 1e-9 for i in range(1, len(ret)))


def test_weakest_beat_is_where_most_listeners_are_lost():
    personas = [_persona(p) for p in ("a", "b", "c")]
    # beat 2 is the pit: low engagement AND everyone skips there
    reports = [
        _report("a", [80, 70, 20, 60], skip=2),
        _report("b", [82, 68, 18, 62], skip=2),
        _report("c", [78, 72, 25, 64], skip=2),
    ]
    v = ve.judge(reports, personas, 4)
    assert v.weakest_beat == 2
    assert v.predicted_drop_pct > 0
    assert "beat 3" in v.headline  # 1-indexed display


def test_deterministic_same_input_same_output():
    personas = [_persona("a"), _persona("b")]
    reports = [_report("a", [50, 40, 60]), _report("b", [55, 35, 65])]
    v1 = ve.judge(reports, personas, 3)
    v2 = ve.judge(reports, personas, 3)
    assert v1.model_dump() == v2.model_dump()


def test_before_after_lift_is_positive_when_beat_improves():
    personas = [_persona(p) for p in ("a", "b")]
    before = ve.judge(
        [_report("a", [80, 20, 70], skip=1), _report("b", [78, 22, 72], skip=1)], personas, 3
    )
    after = ve.judge(
        [_report("a", [80, 75, 70]), _report("b", [78, 74, 72])], personas, 3
    )
    cmp = ve.before_after(before, after, "r1", "r2", 1)
    assert cmp.lift_pct > 0
    assert cmp.after_drop_pct < cmp.before_drop_pct


def test_binge_probability_tracks_final_beat_hook():
    personas = [_persona("a"), _persona("b")]
    weak_ending = ve.judge(
        [_report("a", [70, 70, 10]), _report("b", [72, 72, 12])], personas, 3
    )
    strong_ending = ve.judge(
        [_report("a", [70, 70, 95]), _report("b", [72, 72, 92])], personas, 3
    )
    assert 0.0 <= weak_ending.binge_probability <= 1.0
    assert strong_ending.binge_probability > weak_ending.binge_probability
    # the gauge reads the final beat, not the average
    assert strong_ending.final_hook_score > 80


def test_binge_probability_weights_the_cliffhanger_addict_highest():
    # persona "ravi" has a high binge_weight; a strong final hook from him should
    # move the metric more than the same hook from a low-weight persona.
    ravi = _persona("ravi")
    ravi.binge_weight = 3.0
    quiet = _persona("quiet")
    quiet.binge_weight = 0.5
    personas = [ravi, quiet]
    ravi_loves_ending = ve.judge(
        [_report("ravi", [50, 50, 100]), _report("quiet", [50, 50, 20])], personas, 3
    )
    quiet_loves_ending = ve.judge(
        [_report("ravi", [50, 50, 20]), _report("quiet", [50, 50, 100])], personas, 3
    )
    assert ravi_loves_ending.binge_probability > quiet_loves_ending.binge_probability


def test_degraded_panel_still_produces_verdict():
    # only 1 of 3 personas survived (others failed) — engine must not crash
    personas = [_persona(p) for p in ("a", "b", "c")]
    reports = [_report("a", [60, 30, 70], skip=1)]
    v = ve.judge(reports, personas, 3)
    assert len(v.aggregate_curve) == 3
    assert v.per_persona_summary
