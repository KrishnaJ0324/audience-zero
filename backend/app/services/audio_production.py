"""Audio Production Service (§2.3 component 8).

Two jobs:
  (a) produce_scene — cast the revised scene (speaker→voice map), render each
      line to TTS in a distinct voice, then mix voices + music bed + optional
      SFX into one produced clip.
  (b) speak_verdict — render a persona's verdict to speech in that persona's
      cast voice, so the panel literally speaks its critique on stage.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from ..contracts import PersonaConfig, PersonaReport, ProducedAudio, RevisedScene
from ..providers.factory import Providers

_LINE_RE = re.compile(r"(?m)^\s*([A-Z][A-Za-z .'-]{1,24}):\s*(.*)$")
_SFX_RE = re.compile(r"(?im)^\s*(?:SFX|SOUND)\s*[:\-]\s*(.*)$")


class AudioProductionService:
    def __init__(self, providers: Providers, audio_dir: Path) -> None:
        self.p = providers
        self.dir = audio_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    async def produce_scene(
        self, scene: RevisedScene, personas_voices: dict[str, str] | None = None
    ) -> ProducedAudio:
        voices = personas_voices or {}
        has_sfx = bool(_SFX_RE.search(scene.new_text))
        line_clips: list[str] = []
        casting: dict[str, str] = dict(scene.casting)
        default_pool = ["nova", "onyx", "fable", "echo", "coral", "sage"]
        speaker_idx = 0
        for raw in scene.new_text.splitlines():
            if not raw.strip():
                continue
            if _SFX_RE.match(raw):
                continue  # SFX handled by mixer flag
            m = _LINE_RE.match(raw)
            if m:
                speaker, text = m.group(1).strip(), m.group(2).strip()
            else:
                speaker, text = "NARRATOR", raw.strip()
            if speaker not in casting:
                casting[speaker] = voices.get(speaker) or default_pool[speaker_idx % len(default_pool)]
                speaker_idx += 1
            if not text:
                continue
            clip_name = f"line_{uuid.uuid4().hex[:8]}.wav"
            await self.p.tts.synthesize(text, casting[speaker], str(self.dir / clip_name))
            line_clips.append(str(self.dir / clip_name))

        out_name = f"scene_{scene.beat_index}_{uuid.uuid4().hex[:8]}.wav"
        out = str(self.dir / out_name)
        if line_clips:
            dur = await self.p.mixer.mix(line_clips, out, music=True, sfx=has_sfx)
        else:
            dur = await self.p.tts.synthesize(scene.new_text, "narrator", out)
        # store the basename only; the API serves it at /audio/{filename}
        return ProducedAudio(
            path=out_name, duration_s=round(dur, 2), casting=casting, has_sfx=has_sfx, has_music=True
        )

    async def speak_verdict(self, report: PersonaReport, persona: PersonaConfig) -> str:
        out_name = f"verdict_{persona.id}_{uuid.uuid4().hex[:6]}.wav"
        text = report.verdict_text or f"{persona.name} has no strong objection."
        await self.p.tts.synthesize(text, persona.voice_id, str(self.dir / out_name))
        return out_name
