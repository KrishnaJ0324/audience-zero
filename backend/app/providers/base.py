"""Provider interfaces.

Four external dependencies — LLM judgment, speech-to-text, text-to-speech and
audio mixing — each sit behind a Protocol so they are swappable, mockable and
cacheable. The rest of the system depends only on these signatures, never on a
concrete SDK.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..contracts import (
    Beat,
    Episode,
    PersonaConfig,
    PersonaReport,
    RevisedScene,
)


@runtime_checkable
class LLMJudge(Protocol):
    """Semantic LLM operations used by the pipeline."""

    async def segment(self, transcript: str, min_beats: int, max_beats: int) -> list[Beat]:
        """Split an episode transcript into 10–15 timestamped beats."""
        ...

    async def evaluate(
        self, episode: Episode, beats: list[Beat], persona: PersonaConfig
    ) -> PersonaReport:
        """One agent = one call: score every beat as this persona."""

    async def revise(
        self,
        beat: Beat,
        critiques: list[str],
        speakers: list[str],
    ) -> RevisedScene:
        """Rewrite the weakest scene using the panel's critiques."""


@runtime_checkable
class STTProvider(Protocol):
    async def transcribe(self, audio_bytes: bytes, filename: str) -> tuple[str, float]:
        """Return (transcript, duration_seconds). Timestamps folded into text."""


@runtime_checkable
class TTSProvider(Protocol):
    async def synthesize(self, text: str, voice_id: str, out_path: str) -> float:
        """Render ``text`` to a WAV file at ``out_path``; return duration (s)."""


@runtime_checkable
class AudioMixer(Protocol):
    async def mix(
        self,
        line_clips: list[str],
        out_path: str,
        music: bool = True,
        sfx: bool = False,
    ) -> float:
        """Sequence line clips, duck in a music bed (+ optional SFX). Return dur."""
