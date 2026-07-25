"""Evidence + diagnostics derivation (deterministic).

Turns the panel's reports into concrete, seekable evidence: the exact substrings
in each beat that triggered a drop, mapped to char offsets and interpolated
playback times, plus structured diagnostics (the Evidence Timeline's issue chips
and the collaboration targets for comments/assignment/resolve).

Reuses the lexicons and speaker regex in ``providers/heuristics.py`` so evidence
lines up 1:1 with how the mock scorer actually judged. Model-enrichment (citing
spans via the LLM) is a Phase 3 hook layered on top of these deterministic
spans. IDs are deterministic so the frontend can update idempotently.
"""
from __future__ import annotations

from ..contracts import (
    Diagnostic,
    EvidenceKind,
    EvidenceSpan,
    PanelVerdict,
    PersonaConfig,
    PersonaReport,
    Version,
)
from ..providers import heuristics

_KIND_LEXICON: dict[str, list[str]] = {
    "recap": heuristics.RECAP,
    "trope": heuristics.TROPE,
    "payoff": heuristics.PAYOFF,
    "hook": heuristics.HOOK,
}

_SUMMARY = {
    "recap": "Recap stalls momentum — listeners re-hear what they already know.",
    "crowded": "Too many speakers in one beat — the thread gets hard to follow.",
    "no_hook": "Weak closing hook — little pull into the next episode.",
    "trope": "Cliché / unearned beat — genre-savvy listeners disengage.",
    "boredom": "Low-salience beat — nothing is happening, attention leaks.",
    "hook": "Strong closing hook — drives the next-episode press.",
    "payoff": "Earned payoff — rewards the buildup.",
}

_SEVERITY_BY_KIND = {
    "recap": "major", "crowded": "major", "no_hook": "major",
    "trope": "minor", "boredom": "major", "hook": "info", "payoff": "info",
}


def _find(text: str, phrase: str) -> int:
    return text.lower().find(phrase.lower())


def _time_for(version: Version, beat_index: int, char_start: int, char_end: int, text_len: int):
    beat = next((b for b in version.beats if b.index == beat_index), None)
    if not beat or text_len <= 0:
        return None, None
    span = (beat.end_s or 0) - (beat.start_s or 0)
    s = beat.start_s + (char_start / text_len) * span
    e = beat.start_s + (char_end / text_len) * span
    return round(s, 2), round(e, 2)


def _flaggers(reports: list[PersonaReport], personas: list[PersonaConfig], beat_index: int) -> list[str]:
    thr = {p.id: p.skip_threshold for p in personas}
    out = []
    for r in reports:
        eng = next((s.engagement for s in r.scores if s.beat_index == beat_index), None)
        if r.skip_at_beat == beat_index or (eng is not None and eng < thr.get(r.persona_id, 45)):
            out.append(r.persona_id)
    return out


def spans_and_diagnostics(
    version: Version,
    reports: list[PersonaReport],
    verdict: PanelVerdict | None,
    personas: list[PersonaConfig],
) -> tuple[list[EvidenceSpan], list[Diagnostic]]:
    spans: list[EvidenceSpan] = []
    diagnostics: list[Diagnostic] = []
    n = len(version.beats)
    weakest = verdict.weakest_beat if verdict else -1

    for beat in version.beats:
        i = beat.index
        text = beat.text or beat.summary
        tl = len(text)
        feat = heuristics.extract_features(beat, is_final=(i == n - 1))
        flaggers = _flaggers(reports, personas, i)
        beat_kinds: dict[str, list[str]] = {}  # kind -> span ids on this beat

        def add_span(kind: EvidenceKind, cs: int, ce: int, personas_for: list[str]) -> str:
            sid = f"ev_{i}_{kind}_{len([s for s in spans if s.beat_index == i and s.kind == kind])}"
            s0, s1 = _time_for(version, i, cs, ce, tl)
            spans.append(EvidenceSpan(
                id=sid, beat_index=i, kind=kind,
                char_start=max(0, cs), char_end=min(tl, ce),
                start_s=s0, end_s=s1,
                quote=text[max(0, cs):min(tl, ce)][:160],
                persona_ids=personas_for, source="heuristic",
            ))
            beat_kinds.setdefault(kind, []).append(sid)
            return sid

        # --- lexicon-based spans (recap / trope / payoff / hook) ---
        for kind, lex in _KIND_LEXICON.items():
            for phrase in lex:
                idx = _find(text, phrase)
                if idx >= 0:
                    who = flaggers if kind in ("recap", "trope") else []
                    add_span(kind, idx, idx + len(phrase), who)  # type: ignore[arg-type]
                    break  # one span per kind per beat is enough

        # --- crowded (too many speakers) ---
        if feat["num_chars"] > 3:
            add_span("crowded", 0, min(120, tl), flaggers)

        # --- boredom (nothing happening) ---
        if feat["salience"] < 1.0 and flaggers:
            end = text.find(".")
            add_span("boredom", 0, end + 1 if end > 0 else min(100, tl), flaggers)

        # --- no_hook on the final beat ---
        if i == n - 1 and feat["hook"] < 3.0:
            add_span("no_hook", max(0, tl - 120), tl, flaggers)

        # --- diagnostics: one per issue-kind on this beat ---
        for kind, sid_list in beat_kinds.items():
            if kind in ("hook", "payoff") and i != weakest:
                # positive evidence is shown on the timeline but only the weakest
                # beat's positives become diagnostics-worthy; skip elsewhere
                if kind == "payoff":
                    continue
            sev = _SEVERITY_BY_KIND.get(kind, "minor")
            if i == weakest and kind not in ("hook", "payoff"):
                sev = "critical" if (verdict and verdict.predicted_drop_pct >= 40) else "major"
            elif len(flaggers) >= 3 and kind not in ("hook", "payoff"):
                sev = "major"
            diagnostics.append(Diagnostic(
                id=f"dg_{i}_{kind}",
                beat_index=i,
                type=kind,
                severity=sev,  # type: ignore[arg-type]
                summary=_SUMMARY.get(kind, kind),
                persona_ids=flaggers if kind not in ("hook", "payoff") else [],
                evidence_span_ids=sid_list,
            ))

    # order: weakest beat first, then by severity then beat
    sev_rank = {"critical": 0, "major": 1, "minor": 2, "info": 3}
    diagnostics.sort(key=lambda d: (d.beat_index != weakest, sev_rank.get(d.severity, 9), d.beat_index))
    return spans, diagnostics
