"""Confidence, persona-disagreement, and calibration — pure deterministic
functions (zero LLM calls), consistent with "LLMs judge, code decides".

Built on top of the Verdict Engine's outputs; imported by the pipeline to
assemble the frozen AnalysisRun payload.
"""
from __future__ import annotations

import hashlib
import math

from ..contracts import CalibrationSummary, Confidence, PersonaReport


def disagreement_curve(reports: list[PersonaReport], n_beats: int) -> list[float]:
    """Per-beat spread (max-min engagement across personas), 0..100. High spread
    = the panel disagrees about that beat."""
    curve: list[float] = []
    for i in range(n_beats):
        vals = [
            s.engagement
            for r in reports
            for s in r.scores
            if s.beat_index == i
        ]
        curve.append(float(max(vals) - min(vals)) if len(vals) >= 2 else 0.0)
    return curve


def confidence(
    reports: list[PersonaReport], n_beats: int, n_personas_expected: int
) -> Confidence:
    if not reports:
        return Confidence(label="low")

    mean_conf = sum(r.confidence for r in reports) / len(reports)

    dis = disagreement_curve(reports, n_beats)
    mean_dis = (sum(dis) / len(dis)) if dis else 0.0
    if len(reports) < 2:
        panel_agreement = 0.5  # a single voice can't agree or disagree — unknown
    else:
        # 50 engagement-points of average spread ⇒ zero agreement
        panel_agreement = max(0.0, 1.0 - mean_dis / 50.0)

    # a degraded panel (agents dropped to N−1) is less trustworthy — coverage
    # scales the whole score rather than nudging it.
    coverage = min(1.0, len(reports) / max(n_personas_expected, 1))
    coverage_factor = 0.5 + 0.5 * coverage

    overall = (0.5 * mean_conf + 0.5 * panel_agreement) * coverage_factor
    overall = max(0.0, min(1.0, overall))
    label = "high" if overall >= 0.70 else "moderate" if overall >= 0.45 else "low"

    return Confidence(
        overall=round(overall, 3),
        panel_agreement=round(panel_agreement, 3),
        mean_persona_confidence=round(mean_conf, 3),
        disagreement_curve=[round(x, 1) for x in dis],
        label=label,
    )


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 2:
        return None
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va == 0 or vb == 0:
        return None
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return round(cov / math.sqrt(va * vb), 3)


def simulate_actual(predicted_retention: list[float], seed_key: str) -> list[float]:
    """Deterministically fabricate a plausible 'actual' retention curve for the
    demo: real audiences track the prediction but drift (and tend to drop a bit
    *more* than predicted). Jitter is a stable hash of (seed_key, beat), and the
    result is clamped to a monotonically non-increasing curve in [0, 1]."""
    out: list[float] = []
    running = 1.0
    for i, p in enumerate(predicted_retention):
        h = int(hashlib.sha256(f"{seed_key}|{i}".encode()).hexdigest()[:8], 16)
        unit = (h % 10_000) / 10_000.0            # 0..1
        jitter = (unit - 0.35) * 0.30             # biased slightly negative
        val = max(0.0, min(1.0, p * (1.0 + jitter)))
        running = min(running, val)               # enforce monotonic decline
        out.append(round(running, 4))
    return out


def calibrate(
    predicted_retention: list[float] | None, actual_retention: list[float] | None
) -> CalibrationSummary:
    """Compare predicted vs. real retention (both 0..1, per beat)."""
    if not actual_retention:
        return CalibrationSummary(
            state="uncalibrated", has_actual=False,
            predicted_retention=predicted_retention,
        )
    n = min(len(predicted_retention or []), len(actual_retention))
    pred = (predicted_retention or [])[:n]
    act = actual_retention[:n]
    mae = round(sum(abs(pred[i] - act[i]) for i in range(n)) / n, 4) if n else None
    corr = _pearson(pred, act)
    return CalibrationSummary(
        state="calibrated",
        has_actual=True,
        predicted_retention=predicted_retention,
        actual_retention=actual_retention,
        mae=mae,
        correlation=corr,
    )
