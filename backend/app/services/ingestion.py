"""Ingestion Service (§2.3 component 1) + Beat Segmenter (component 2).

Normalises both inputs — pasted script text (primary) or an uploaded audio file
(secondary, via STT with timestamps) — into a single Episode object with beats.
"""
from __future__ import annotations

import uuid

from ..contracts import Episode
from ..providers.factory import Providers


class IngestionService:
    def __init__(self, providers: Providers, min_beats: int, max_beats: int) -> None:
        self.p = providers
        self.min_beats = min_beats
        self.max_beats = max_beats

    async def ingest_script(self, title: str, script_text: str) -> Episode:
        beats = await self.p.llm.segment(script_text, self.min_beats, self.max_beats)
        duration = beats[-1].end_s if beats else None
        return Episode(
            id=f"ep_{uuid.uuid4().hex[:10]}",
            title=title or "Untitled Episode",
            source_type="script",
            transcript=script_text,
            duration_s=duration,
            beats=beats,
        )

    async def ingest_audio(self, title: str, audio_bytes: bytes, filename: str) -> Episode:
        transcript, duration = await self.p.stt.transcribe(audio_bytes, filename)
        beats = await self.p.llm.segment(transcript, self.min_beats, self.max_beats)
        # rescale synthetic beat timeline onto the real audio duration so drop
        # markers land on real playback time ("we test what listeners hear").
        if beats and duration:
            span = beats[-1].end_s or duration
            k = duration / span if span else 1.0
            for b in beats:
                b.start_s = round(b.start_s * k, 2)
                b.end_s = round(b.end_s * k, 2)
        return Episode(
            id=f"ep_{uuid.uuid4().hex[:10]}",
            title=title or "Audio Episode",
            source_type="audio",
            transcript=transcript,
            duration_s=duration,
            beats=beats,
        )
