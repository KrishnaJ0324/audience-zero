"""Data contracts (Pydantic).

Per §2.4 of the build plan these are frozen on Day 0 — everything else can
drift, but every component communicates through exactly these typed models. No
component imports another component's internals.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Input / episode
# --------------------------------------------------------------------------- #


class Beat(BaseModel):
    index: int
    start_s: float
    end_s: float
    summary: str
    text: str


class Episode(BaseModel):
    id: str
    title: str
    source_type: Literal["script", "audio"]
    transcript: str
    duration_s: float | None = None
    beats: list[Beat] = Field(default_factory=list)


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
    skip_threshold: int = 45  # engagement below this => this persona skips
    # taste-profile knobs consumed by both the persona prompt and the (mock)
    # heuristic scorer. Free-form floats in [-1, 1] unless noted.
    weights: dict[str, float] = Field(default_factory=dict)
    # audience weight in the aggregate curve (Ananya is a small but loud voice)
    audience_weight: float = 1.0
    # weight of this persona's final-beat reaction in the Binge Probability
    # metric (§2.10 — Ravi, the cliffhanger addict, is weighted highest)
    binge_weight: float = 1.0
    color: str = "#38bdf8"  # dashboard curve colour


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
    verdict_audio_path: str | None = None  # populated by Audio Production


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
    # retention curve derived from the aggregate engagement curve (0..1)
    retention_curve: list[float] = Field(default_factory=list)
    # Binge Probability (§2.10, P5 "Cliffhanger Optimizer"): likelihood a
    # listener hits play on the next episode, driven by final-beat hook
    # strength, binge-weighted across personas (Ravi highest). 0..1.
    binge_probability: float = 0.0
    # engagement at the final beat (the hook), audience-weighted — feeds the gauge
    final_hook_score: float = 0.0


# --------------------------------------------------------------------------- #
# Revision + audio
# --------------------------------------------------------------------------- #


class RevisedScene(BaseModel):
    beat_index: int
    new_text: str
    change_rationale: str
    casting: dict[str, str] = Field(default_factory=dict)  # speaker -> voice_id


class ProducedAudio(BaseModel):
    path: str
    duration_s: float
    casting: dict[str, str] = Field(default_factory=dict)
    has_sfx: bool = False
    has_music: bool = True


class AudioClip(BaseModel):
    path: str
    duration_s: float


# --------------------------------------------------------------------------- #
# Session / run aggregate
# --------------------------------------------------------------------------- #


class PanelRun(BaseModel):
    id: str
    episode_id: str
    status: Literal["pending", "running", "complete", "failed"] = "pending"
    verdict: PanelVerdict | None = None
    reports: list[PersonaReport] = Field(default_factory=list)
    revised_scene: RevisedScene | None = None
    produced_audio: ProducedAudio | None = None
    revision_target: Literal["weakest", "ending"] = "weakest"
    parent_run_id: str | None = None  # parent -> before/after comparison
    created_at: str = ""
    # denormalised for convenient before/after rendering
    episode_title: str = ""


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
    lift_pct: float  # positive = improvement at the fixed beat
    # binge probability before/after (the headline metric for an ending fix)
    before_binge: float = 0.0
    after_binge: float = 0.0
    binge_lift_pct: float = 0.0


class PopulationSweep(BaseModel):
    """Extrapolation from 6 calibrated archetypes to a crowd of sampled
    listeners (§2.10). Deterministic — trait-seeds are jittered by a stable hash,
    so the histogram is reproducible and needs no live model calls."""

    episode_id: str
    n: int
    n_beats: int
    drop_histogram: list[int]  # per-beat count of listeners whose first drop is here
    completed: int  # sampled listeners who reached the end
    modal_drop_beat: int
    completion_rate: float
    per_archetype: dict[str, float] = Field(default_factory=dict)  # id -> mean drop beat
