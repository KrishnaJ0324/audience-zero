"""Data contracts (Pydantic).

Frozen, typed models every component communicates through. v2 introduces the
producer-workflow hierarchy — Project -> Episode -> Version -> AnalysisRun ->
RevisionVariant — and freezes the AnalysisRun payload
(verdict+confidence, evidence_spans, diagnostics, revision_variants,
run_manifest, calibration_summary) so features can be built against it.

Naming note: the transcript+beats object (formerly ``Episode``) is now
``Version`` — the concrete, analyzable unit. ``Episode`` is the lightweight
logical grouping of versions inside a project.
"""
from __future__ import annotations

import datetime as _dt
from typing import Literal

from pydantic import BaseModel, Field


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Input / content
# --------------------------------------------------------------------------- #


class Beat(BaseModel):
    index: int
    start_s: float
    end_s: float
    summary: str
    text: str


class Version(BaseModel):
    """A concrete, analyzable transcript+beats (script or produced audio). The
    unit an AnalysisRun scores. Formerly ``Episode``."""

    id: str
    title: str
    source_type: Literal["script", "audio"]
    transcript: str
    duration_s: float | None = None
    beats: list[Beat] = Field(default_factory=list)
    # hierarchy links (optional so the low-level engine can build bare Versions)
    project_id: str = ""
    episode_id: str = ""
    label: str = "v1"
    parent_version_id: str | None = None
    created_at: str = Field(default_factory=_now)


# Back-compat alias: low-level engine files were written against ``Episode``.
Episode = Version


class Project(BaseModel):
    id: str
    name: str
    description: str = ""
    created_at: str = Field(default_factory=_now)


class EpisodeMeta(BaseModel):
    """Logical episode — groups its versions inside a project. Exposed in the API
    as an 'episode'."""

    id: str
    project_id: str
    title: str
    created_at: str = Field(default_factory=_now)


# --------------------------------------------------------------------------- #
# Personas
# --------------------------------------------------------------------------- #


class PersonaConfig(BaseModel):
    id: str
    name: str
    archetype: str
    model: str  # e.g. "gpt-4o" | "gpt-4o-mini" — per-agent model diversity
    system_prompt: str
    tools: list[str] = Field(default_factory=list)
    voice_id: str
    skip_threshold: int = 45
    weights: dict[str, float] = Field(default_factory=dict)
    audience_weight: float = 1.0
    binge_weight: float = 1.0
    color: str = "#38bdf8"
    # user-defined personas (created at runtime, stored in the DB)
    custom: bool = False
    enabled: bool = True
    created_at: str = ""


# --------------------------------------------------------------------------- #
# Persona output
# --------------------------------------------------------------------------- #


class BeatScore(BaseModel):
    beat_index: int
    engagement: int = Field(ge=0, le=100)


class PersonaReport(BaseModel):
    persona_id: str
    scores: list[BeatScore]
    skip_at_beat: int | None = None
    drop_reason: str = ""
    verdict_text: str = ""
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    verdict_audio_path: str | None = None


# --------------------------------------------------------------------------- #
# Verdict (deterministic engine output)
# --------------------------------------------------------------------------- #


class PerPersonaSummary(BaseModel):
    persona_id: str
    persona_name: str
    skip_at_beat: int | None
    mean_engagement: float
    verdict_text: str


class PanelVerdict(BaseModel):
    aggregate_curve: list[float]
    weakest_beat: int
    predicted_drop_pct: float
    per_persona_summary: list[PerPersonaSummary]
    headline: str
    retention_curve: list[float] = Field(default_factory=list)
    binge_probability: float = 0.0
    final_hook_score: float = 0.0


# --------------------------------------------------------------------------- #
# Confidence / disagreement (NEW — deterministic, from reports)
# --------------------------------------------------------------------------- #


class Confidence(BaseModel):
    overall: float = 0.0            # 0..1
    panel_agreement: float = 0.0    # 1 - normalised per-beat spread
    mean_persona_confidence: float = 0.0
    disagreement_curve: list[float] = Field(default_factory=list)  # per-beat spread 0..100
    label: Literal["low", "moderate", "high"] = "moderate"


# --------------------------------------------------------------------------- #
# Evidence + diagnostics (NEW)
# --------------------------------------------------------------------------- #

EvidenceKind = Literal["recap", "crowded", "no_hook", "trope", "boredom", "hook", "payoff"]


class EvidenceSpan(BaseModel):
    id: str
    beat_index: int
    kind: EvidenceKind
    start_s: float | None = None
    end_s: float | None = None
    char_start: int = 0
    char_end: int = 0
    quote: str = ""
    persona_ids: list[str] = Field(default_factory=list)
    source: Literal["heuristic", "model"] = "heuristic"


class Comment(BaseModel):
    id: str
    author: str = "producer"
    body: str
    created_at: str = Field(default_factory=_now)


class Diagnostic(BaseModel):
    id: str
    beat_index: int
    type: str                       # evidence kind or "drop"
    severity: Literal["info", "minor", "major", "critical"] = "minor"
    summary: str = ""
    persona_ids: list[str] = Field(default_factory=list)
    evidence_span_ids: list[str] = Field(default_factory=list)
    status: Literal["open", "resolved", "dismissed"] = "open"
    assignee: str | None = None
    comments: list[Comment] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Revision + audio
# --------------------------------------------------------------------------- #


class RevisedScene(BaseModel):
    beat_index: int
    new_text: str
    change_rationale: str
    casting: dict[str, str] = Field(default_factory=dict)


class ProducedAudio(BaseModel):
    path: str
    duration_s: float
    casting: dict[str, str] = Field(default_factory=dict)
    has_sfx: bool = False
    has_music: bool = True


class AudioClip(BaseModel):
    path: str
    duration_s: float


class AudioDisclosure(BaseModel):
    """Shown wherever generated audio plays."""

    ai_generated: bool = True
    voice_consent: Literal[
        "synthetic_no_consent_needed", "consented", "pending", "unknown"
    ] = "synthetic_no_consent_needed"
    note: str = "Voices are AI-generated (synthetic — no real person was cloned)."


class RevisionVariant(BaseModel):
    id: str
    target: Literal["weakest", "ending", "custom"] = "weakest"
    beat_index: int
    new_text: str
    change_rationale: str = ""
    casting: dict[str, str] = Field(default_factory=dict)
    produced_audio: ProducedAudio | None = None
    before_after: "BeforeAfter | None" = None
    status: Literal["proposed", "accepted", "rejected"] = "proposed"
    notes: str = ""
    rerun_id: str | None = None
    disclosure: AudioDisclosure = Field(default_factory=AudioDisclosure)
    created_at: str = Field(default_factory=_now)


# --------------------------------------------------------------------------- #
# Reproducibility + calibration (NEW)
# --------------------------------------------------------------------------- #


class RunManifest(BaseModel):
    run_id: str
    provider: str = "mock"
    models: dict[str, str] = Field(default_factory=dict)   # role/persona -> model
    persona_ids: list[str] = Field(default_factory=list)
    reveal_delay_s: float = 0.0
    seed_signature: str = ""
    engine_version: str = ""
    started_at: str = ""
    finished_at: str | None = None
    duration_s: float | None = None
    cost_estimate_usd: float | None = None


class CalibrationSummary(BaseModel):
    state: Literal["uncalibrated", "calibrated"] = "uncalibrated"
    has_actual: bool = False
    predicted_retention: list[float] | None = None
    actual_retention: list[float] | None = None
    mae: float | None = None
    correlation: float | None = None
    per_persona_calibration: dict[str, float] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Job state (NEW)
# --------------------------------------------------------------------------- #


class JobState(BaseModel):
    status: Literal["queued", "running", "failed", "complete"] = "queued"
    stage: str = ""                 # segmenting|scoring|verdict|producing|done
    progress: float = 0.0           # 0..1
    attempts: int = 0
    max_attempts: int = 2
    error: str | None = None
    updated_at: str = Field(default_factory=_now)


# --------------------------------------------------------------------------- #
# Analysis run aggregate (supersedes PanelRun) — THE frozen payload
# --------------------------------------------------------------------------- #


class AnalysisRun(BaseModel):
    id: str
    project_id: str = ""
    episode_id: str = ""
    version_id: str = ""
    parent_run_id: str | None = None
    created_at: str = Field(default_factory=_now)

    job: JobState = Field(default_factory=JobState)
    # legacy top-level status mirror (kept until the FE migrates to `job`)
    status: Literal["pending", "running", "complete", "failed"] = "pending"

    # --- frozen payload ---
    verdict: PanelVerdict | None = None
    confidence: Confidence | None = None
    reports: list[PersonaReport] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    revision_variants: list[RevisionVariant] = Field(default_factory=list)
    run_manifest: RunManifest | None = None
    calibration_summary: CalibrationSummary | None = None

    # --- legacy convenience mirrors (newest variant; drop after FE migration) -
    revised_scene: RevisedScene | None = None
    produced_audio: ProducedAudio | None = None
    revision_target: Literal["weakest", "ending"] = "weakest"

    # denormalised for lists / cards
    episode_title: str = ""
    version_label: str = ""


# Back-compat alias for any lingering imports.
PanelRun = AnalysisRun


# --------------------------------------------------------------------------- #
# Comparison payload (before/after)
# --------------------------------------------------------------------------- #


class BeforeAfter(BaseModel):
    before_run_id: str
    after_run_id: str
    beat_index: int
    target: Literal["weakest", "ending"] = "weakest"
    before_curve: list[float]
    after_curve: list[float]
    before_drop_pct: float
    after_drop_pct: float
    lift_pct: float
    before_binge: float = 0.0
    after_binge: float = 0.0
    binge_lift_pct: float = 0.0


class PopulationSweep(BaseModel):
    """Extrapolation from 6 calibrated archetypes to a crowd of sampled
    listeners. Deterministic — trait-seeds jittered by a stable hash."""

    episode_id: str
    n: int
    n_beats: int
    drop_histogram: list[int]
    completed: int
    modal_drop_beat: int
    completion_rate: float
    per_archetype: dict[str, float] = Field(default_factory=dict)


# resolve forward reference (RevisionVariant -> BeforeAfter)
RevisionVariant.model_rebuild()
