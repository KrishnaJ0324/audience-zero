"""Phase 1 gate tests: the frozen AnalysisRun payload, confidence/disagreement
math, evidence-span offsets, and manifest determinism."""
from __future__ import annotations

import asyncio

from app.config import get_settings
from app.contracts import BeatScore, PersonaConfig, PersonaReport
from app.pipeline import Pipeline
from app.services import analysis


def _run(script: str = "demo_episode.txt"):
    async def _go():
        s = get_settings()
        s.provider = "mock"
        s.reveal_delay_s = 0.0
        p = Pipeline(settings=s)
        await p.init()
        text = (s.scripts_dir / script).read_text(encoding="utf-8")
        v = await p.ingest_script(script, text)
        run = await p.run_panel(v, p.new_run_id(), speak_verdicts=0)
        return v, run

    return asyncio.run(_go())


# --- frozen payload -------------------------------------------------------- #
def test_frozen_payload_is_fully_populated():
    version, run = _run()
    assert run.project_id and run.episode_id and run.version_id == version.id
    assert run.verdict is not None
    assert run.confidence is not None
    assert run.reports
    assert run.evidence_spans          # non-empty
    assert run.diagnostics             # non-empty
    assert run.revision_variants == []  # none until revised
    assert run.run_manifest is not None
    assert run.calibration_summary is not None
    assert run.calibration_summary.state == "uncalibrated"
    assert run.job.status == "complete"


def test_diagnostics_reference_real_spans():
    _, run = _run()
    span_ids = {s.id for s in run.evidence_spans}
    for d in run.diagnostics:
        for sid in d.evidence_span_ids:
            assert sid in span_ids
        assert d.status == "open"


# --- confidence / disagreement --------------------------------------------- #
def _persona(pid):
    return PersonaConfig(id=pid, name=pid, archetype="t", model="mock",
                         system_prompt="", voice_id=f"{pid}_v")


def _report(pid, curve):
    return PersonaReport(
        persona_id=pid,
        scores=[BeatScore(beat_index=i, engagement=e) for i, e in enumerate(curve)],
    )


def test_confidence_high_when_panel_agrees():
    personas = [_persona("a"), _persona("b")]
    reports = [_report("a", [70, 70, 70]), _report("b", [70, 70, 70])]
    for r in reports:
        r.confidence = 0.9
    c = analysis.confidence(reports, 3, 2)
    assert c.panel_agreement == 1.0
    assert c.label == "high"
    assert all(x == 0.0 for x in c.disagreement_curve)


def test_confidence_drops_with_disagreement_and_partial_panel():
    personas = [_persona(p) for p in ("a", "b", "c")]
    # only 1 of 3 reported, and it's a wide curve → low coverage
    c = analysis.confidence([_report("a", [90, 10, 80])], 3, 3)
    assert c.overall < 0.7
    assert len(c.disagreement_curve) == 3


def test_calibration_mae_and_state():
    cal = analysis.calibrate([1.0, 0.8, 0.5], [1.0, 0.7, 0.4])
    assert cal.state == "calibrated" and cal.has_actual
    assert abs(cal.mae - 0.0667) < 0.01
    uncal = analysis.calibrate([1.0, 0.8], None)
    assert uncal.state == "uncalibrated"


# --- evidence offsets ------------------------------------------------------ #
def test_evidence_spans_map_inside_their_beat_text():
    version, run = _run()
    beats = {b.index: b for b in version.beats}
    for s in run.evidence_spans:
        b = beats[s.beat_index]
        tl = len(b.text or b.summary)
        assert 0 <= s.char_start <= s.char_end <= tl
        if s.start_s is not None:
            assert b.start_s - 0.01 <= s.start_s <= b.end_s + 0.01


# --- manifest determinism -------------------------------------------------- #
def test_manifest_seed_is_deterministic_for_same_version():
    async def _go():
        s = get_settings()
        s.provider = "mock"; s.reveal_delay_s = 0.0
        p = Pipeline(settings=s)
        await p.init()
        text = (s.scripts_dir / "demo_episode.txt").read_text(encoding="utf-8")
        v = await p.ingest_script("demo", text)
        r1 = await p.run_panel(v, p.new_run_id(), speak_verdicts=0)
        r2 = await p.run_panel(v, p.new_run_id(), speak_verdicts=0)
        return r1, r2

    r1, r2 = asyncio.run(_go())
    assert r1.run_manifest.seed_signature == r2.run_manifest.seed_signature
    assert r1.run_manifest.provider == "mock"
    assert r1.run_manifest.persona_ids
