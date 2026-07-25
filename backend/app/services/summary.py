"""Concise producer summary — deterministic (model-enrichment is a Phase 3 hook).

Turns an AnalysisRun into a few plain-English sentences a producer can read at a
glance or paste into a report.
"""
from __future__ import annotations

from ..contracts import AnalysisRun


def producer_summary(run: AnalysisRun) -> str:
    v = run.verdict
    if not v:
        return "Analysis is still running — no verdict yet."

    title = run.episode_title or "This episode"
    lines: list[str] = []

    drop = v.predicted_drop_pct
    beat = v.weakest_beat + 1
    lines.append(
        f"{title} is predicted to lose ~{drop:.0f}% of listeners at beat {beat}, "
        f"its weakest point."
    )

    binge = round(v.binge_probability * 100)
    hook_word = "strong" if binge >= 66 else "soft" if binge >= 40 else "weak"
    lines.append(f"Binge probability is {binge}% (a {hook_word} closing hook).")

    if run.confidence:
        lines.append(
            f"Panel confidence is {run.confidence.label} "
            f"({round(run.confidence.overall * 100)}%), with "
            f"{round(run.confidence.panel_agreement * 100)}% agreement across the six listeners."
        )

    top = next((d for d in run.diagnostics if d.beat_index == v.weakest_beat), None) \
        or (run.diagnostics[0] if run.diagnostics else None)
    if top:
        who = f"{len(top.persona_ids)} of six listeners" if top.persona_ids else "the panel"
        lines.append(f"Top issue — {top.summary} Flagged by {who}.")

    accepted = next((x for x in run.revision_variants if x.status == "accepted"), None)
    proposed = accepted or (run.revision_variants[-1] if run.revision_variants else None)
    if proposed and proposed.before_after:
        ba = proposed.before_after
        if ba.target == "ending":
            lines.append(
                f"Recommended fix: strengthen the ending → projected "
                f"+{ba.binge_lift_pct:.0f}pt binge probability."
            )
        else:
            lines.append(
                f"Recommended fix: rewrite beat {proposed.beat_index + 1} "
                f"({proposed.change_rationale.split('.')[0].lower() or 'tighten it'}) → "
                f"projected +{ba.lift_pct:.0f}pt retention at that beat."
            )
    elif proposed:
        lines.append(
            f"A revision for beat {proposed.beat_index + 1} is ready to re-run for a before/after."
        )

    return " ".join(lines)
