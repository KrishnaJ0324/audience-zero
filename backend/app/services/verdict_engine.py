"""Verdict Engine — pure, deterministic, zero LLM calls (§2.3 component 6).

"LLMs judge, deterministic code decides." Every headline number the demo puts
on screen is computed here from the panel's PersonaReports by a pure function.
Reproducible, unit-testable, and defensible in Q&A ("how is this computed?").

Retention model
---------------
We simulate an audience of size 1.0 walking through the episode. At each beat a
share of the *currently remaining* listeners churns:

    churn_i = SKIP_WEIGHT * skip_share_i + soft_leak_i

* ``skip_share_i`` — audience-weighted fraction of personas whose skip point is
  exactly this beat (a hard "I'm out here").
* ``soft_leak_i``  — gentle bleed when aggregate engagement dips below a comfort
  threshold, even if nobody formally skips.

``retention_i = retention_{i-1} * (1 - churn_i)``. The weakest beat is where the
most listeners are lost (max churn), and the headline drop % is that beat's
churn expressed as a percentage of the listeners who reached it.
"""
from __future__ import annotations

from ..contracts import (
    BeforeAfter,
    PanelVerdict,
    PersonaConfig,
    PersonaReport,
    PerPersonaSummary,
)

SOFT_THRESHOLD = 55.0  # aggregate engagement below which soft leak begins
SOFT_K = 0.9
SKIP_WEIGHT = 0.8
MAX_CHURN = 0.85


def _weights(personas: list[PersonaConfig]) -> dict[str, float]:
    return {p.id: max(p.audience_weight, 0.0) for p in personas}


def aggregate_curve(
    reports: list[PersonaReport], personas: list[PersonaConfig], n_beats: int
) -> list[float]:
    """Audience-weighted mean engagement per beat (0..100)."""
    w = _weights(personas)
    curve: list[float] = []
    for i in range(n_beats):
        num = den = 0.0
        for r in reports:
            wi = w.get(r.persona_id, 1.0)
            score = next((s.engagement for s in r.scores if s.beat_index == i), None)
            if score is not None:
                num += wi * score
                den += wi
        curve.append(round(num / den, 2) if den else 0.0)
    return curve


def _churn_series(
    reports: list[PersonaReport], personas: list[PersonaConfig], curve: list[float]
) -> list[float]:
    w = _weights(personas)
    total_w = sum(w.values()) or 1.0
    n = len(curve)
    churn = [0.0] * n
    for i in range(n):
        skip_w = sum(w.get(r.persona_id, 1.0) for r in reports if r.skip_at_beat == i)
        skip_share = skip_w / total_w
        soft = max(0.0, (SOFT_THRESHOLD - curve[i]) / 100.0) * SOFT_K
        c = SKIP_WEIGHT * skip_share + soft
        churn[i] = min(MAX_CHURN, max(0.0, c))
    churn[0] = 0.0  # nobody churns before the episode starts
    return churn


def retention_from_churn(churn: list[float]) -> list[float]:
    r = 1.0
    out = []
    for c in churn:
        r *= (1.0 - c)
        out.append(round(r, 4))
    return out


def binge_probability(
    reports: list[PersonaReport], personas: list[PersonaConfig], n_beats: int
) -> tuple[float, float]:
    """Binge Probability + raw final-hook score (§2.10).

    The final beat is the hook that decides whether a listener presses play on
    the next episode. We take each persona's engagement at that beat, weight it
    by the persona's ``binge_weight`` (the cliffhanger addict counts most), and
    normalise to a 0..1 probability. Pure and deterministic, like every other
    headline number.
    """
    if n_beats == 0:
        return 0.0, 0.0
    last = n_beats - 1
    bw = {p.id: max(p.binge_weight, 0.0) for p in personas}
    num = den = 0.0
    for r in reports:
        w = bw.get(r.persona_id, 1.0)
        eng = next((s.engagement for s in r.scores if s.beat_index == last), None)
        if eng is not None:
            num += w * eng
            den += w
    hook = (num / den) if den else 0.0
    return round(hook / 100.0, 3), round(hook, 1)


def judge(
    reports: list[PersonaReport], personas: list[PersonaConfig], n_beats: int
) -> PanelVerdict:
    curve = aggregate_curve(reports, personas, n_beats)
    churn = _churn_series(reports, personas, curve)
    retention = retention_from_churn(churn)

    weakest = max(range(n_beats), key=lambda i: churn[i]) if n_beats else 0
    predicted_drop_pct = round(churn[weakest] * 100.0, 1)
    binge_p, final_hook = binge_probability(reports, personas, n_beats)

    pmap = {p.id: p for p in personas}
    summaries: list[PerPersonaSummary] = []
    for r in reports:
        p = pmap.get(r.persona_id)
        mean_eng = round(sum(s.engagement for s in r.scores) / len(r.scores), 1) if r.scores else 0.0
        summaries.append(
            PerPersonaSummary(
                persona_id=r.persona_id,
                persona_name=p.name if p else r.persona_id,
                skip_at_beat=r.skip_at_beat,
                mean_engagement=mean_eng,
                verdict_text=r.verdict_text,
            )
        )

    # weakest_beat stays 0-indexed for array access; humans count from 1.
    headline = f"Predicted {predicted_drop_pct:.0f}% listener drop at beat {weakest + 1}"
    return PanelVerdict(
        aggregate_curve=curve,
        weakest_beat=weakest,
        predicted_drop_pct=predicted_drop_pct,
        per_persona_summary=summaries,
        headline=headline,
        retention_curve=retention,
        binge_probability=binge_p,
        final_hook_score=final_hook,
    )


def before_after(
    before: PanelVerdict,
    after: PanelVerdict,
    before_run_id: str,
    after_run_id: str,
    beat_index: int,
    target: str = "weakest",
) -> BeforeAfter:
    """Lift at the fixed beat: reduction in drop % (percentage points), plus the
    change in Binge Probability (the headline for an ending fix)."""
    b_drop = _drop_at(before, beat_index)
    a_drop = _drop_at(after, beat_index)
    return BeforeAfter(
        before_run_id=before_run_id,
        after_run_id=after_run_id,
        beat_index=beat_index,
        target=target,  # type: ignore[arg-type]
        before_curve=before.aggregate_curve,
        after_curve=after.aggregate_curve,
        before_drop_pct=b_drop,
        after_drop_pct=a_drop,
        lift_pct=round(b_drop - a_drop, 1),
        before_binge=round(before.binge_probability * 100, 1),
        after_binge=round(after.binge_probability * 100, 1),
        binge_lift_pct=round((after.binge_probability - before.binge_probability) * 100, 1),
    )


def _drop_at(v: PanelVerdict, beat_index: int) -> float:
    r = v.retention_curve
    if not r or beat_index <= 0 or beat_index >= len(r):
        return v.predicted_drop_pct if beat_index == v.weakest_beat else 0.0
    prev = r[beat_index - 1] or 1.0
    return round((prev - r[beat_index]) / prev * 100.0, 1)
