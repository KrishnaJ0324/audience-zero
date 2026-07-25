"""Real OpenAI adapters.

Only imported/instantiated when a key is present. Structured outputs are
enforced so persona reports always satisfy the frozen schema (§2.6 — "all
agents emit the identical PersonaReport schema or the Verdict Engine breaks").
Falls back to the deterministic heuristic if the model returns something
unparseable, so a flaky call degrades gracefully rather than blocking the panel.
"""
from __future__ import annotations

import json
import tempfile

from ..config import Settings
from ..contracts import Beat, BeatScore, Episode, PersonaConfig, PersonaReport, RevisedScene
from . import heuristics
from .mock import MockTTS
from .wavtools import write_wav
from .wavtools import speak as _mock_speak


def _client(settings: Settings):
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=settings.effective_openai_key)


class OpenAILLM:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.client = _client(settings)

    async def segment(self, transcript: str, min_beats: int, max_beats: int) -> list[Beat]:
        sys = (
            "You are a story editor. Split the episode into between "
            f"{min_beats} and {max_beats} sequential beats. A beat is one "
            "dramatic unit. Return STRICT JSON: {\"beats\":[{\"summary\":str,"
            "\"text\":str}]}. Preserve original wording in text."
        )
        resp = await self.client.chat.completions.create(
            model=self.s.segmenter_model,
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": transcript}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        raw = data.get("beats", [])[:max_beats] or [{"summary": "scene", "text": transcript}]
        total = max(len(transcript.split()) / 2.4, 60.0)
        per = total / len(raw)
        return [
            Beat(
                index=i,
                start_s=round(i * per, 2),
                end_s=round((i + 1) * per, 2),
                summary=b.get("summary", "scene")[:120],
                text=b.get("text", ""),
            )
            for i, b in enumerate(raw)
        ]

    async def evaluate(
        self, episode: Episode, beats: list[Beat], persona: PersonaConfig
    ) -> PersonaReport:
        beat_block = "\n".join(f"[Beat {b.index}] {b.text}" for b in beats)
        sys = (
            persona.system_prompt
            + "\n\nScore EVERY beat's engagement 0-100 from YOUR taste only. "
            "Return STRICT JSON: {\"scores\":[{\"beat_index\":int,"
            "\"engagement\":int}],\"skip_at_beat\":int|null,\"drop_reason\":str,"
            "\"verdict_text\":str,\"confidence\":number}. verdict_text is one "
            "sentence, in your voice, said aloud."
        )
        try:
            resp = await self.client.chat.completions.create(
                model=persona.model or self.s.default_persona_model,
                messages=[{"role": "system", "content": sys}, {"role": "user", "content": beat_block}],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            valid = {b.index for b in beats}
            scores = [
                BeatScore(beat_index=int(s["beat_index"]), engagement=int(s["engagement"]))
                for s in data.get("scores", [])
                if int(s.get("beat_index", -1)) in valid
            ]
            if len(scores) != len(beats):  # incomplete => fall back deterministically
                raise ValueError("incomplete scores")
            return PersonaReport(
                persona_id=persona.id,
                scores=sorted(scores, key=lambda s: s.beat_index),
                skip_at_beat=data.get("skip_at_beat"),
                drop_reason=str(data.get("drop_reason", ""))[:200],
                verdict_text=str(data.get("verdict_text", ""))[:280],
                confidence=float(data.get("confidence", 0.6)),
            )
        except Exception:
            return heuristics.make_report(persona, episode, beats)

    async def chat_persona(self, messages: list[dict]) -> dict:
        """Conversational persona designer. Returns {reply, draft} every turn."""
        sys = (
            "You are a persona designer for a synthetic audio test-audience. Help the "
            "user craft ONE listener persona that will score audio-drama/podcast beats. "
            "Converse naturally to refine tastes, patience, and what makes them skip. "
            "On EVERY turn return STRICT JSON: {\"reply\": str, \"draft\": {\"name\": str, "
            "\"archetype\": str, \"system_prompt\": str, \"ready\": bool}}. The "
            "system_prompt is second-person ('You are …'), 2-4 sentences, and instructs "
            "them to score each beat 0-100 from their taste. Set ready=true once the "
            "persona is coherent enough to save."
        )
        convo = [{"role": "system", "content": sys}] + [
            {"role": m["role"], "content": m["content"]}
            for m in messages if m.get("role") in ("user", "assistant")
        ]
        try:
            resp = await self.client.chat.completions.create(
                model=self.s.segmenter_model, messages=convo,
                response_format={"type": "json_object"}, temperature=0.7,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            d = data.get("draft") or {}
            return {
                "reply": str(data.get("reply", "")),
                "draft": {
                    "name": str(d.get("name", "")),
                    "archetype": str(d.get("archetype", "Custom listener")),
                    "system_prompt": str(d.get("system_prompt", "")),
                    "ready": bool(d.get("ready", False)),
                },
            }
        except Exception as exc:
            return {
                "reply": f"(model error — {str(exc)[:80]}) You can still fill the fields manually.",
                "draft": {"name": "", "archetype": "Custom listener", "system_prompt": "", "ready": False},
            }

    async def summarize(self, deterministic: str) -> str:
        """Polish the deterministic producer summary (numbers must stay exact)."""
        try:
            resp = await self.client.chat.completions.create(
                model=self.s.segmenter_model,
                messages=[
                    {"role": "system", "content":
                        "Rewrite this audio-episode analysis for a busy producer in 2–3 "
                        "crisp sentences. Keep every number and beat reference exact. No hype."},
                    {"role": "user", "content": deterministic},
                ],
                temperature=0.4,
            )
            return (resp.choices[0].message.content or deterministic).strip()
        except Exception:
            return deterministic

    async def cite_evidence(self, beat_text: str, reason: str) -> list[str]:
        """Ask the model to cite up to 2 verbatim phrases behind a drop."""
        try:
            resp = await self.client.chat.completions.create(
                model=self.s.default_persona_model,
                messages=[
                    {"role": "system", "content":
                        "Quote up to 2 SHORT verbatim phrases from the scene that a listener "
                        f"would find '{reason}'. Phrases must appear VERBATIM in the text. "
                        "Return STRICT JSON: {\"quotes\":[str]}."},
                    {"role": "user", "content": beat_text[:2000]},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            return [str(q) for q in data.get("quotes", [])][:2]
        except Exception:
            return []

    async def revise(
        self, beat: Beat, critiques: list[str], speakers: list[str]
    ) -> RevisedScene:
        sys = (
            "You are a script doctor. Rewrite ONLY this one scene to fix the "
            "panel's critiques. Keep it the same length, max 3 speakers, add a "
            "closing hook. Return STRICT JSON: {\"new_text\":str,"
            "\"change_rationale\":str,\"casting\":{speaker:voice_hint}}."
        )
        user = f"SCENE:\n{beat.text}\n\nCRITIQUES:\n- " + "\n- ".join(critiques)
        try:
            resp = await self.client.chat.completions.create(
                model=self.s.revision_model,
                messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                temperature=0.8,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            return RevisedScene(
                beat_index=beat.index,
                new_text=data.get("new_text", beat.text),
                change_rationale=data.get("change_rationale", ""),
                casting=data.get("casting", {}),
            )
        except Exception:
            from .mock import MockLLM

            return await MockLLM().revise(beat, critiques, speakers)


class OpenAISTT:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.client = _client(settings)

    async def transcribe(self, audio_bytes: bytes, filename: str) -> tuple[str, float]:
        suffix = "." + (filename.rsplit(".", 1)[-1] if "." in filename else "mp3")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            tmp = f.name
        with open(tmp, "rb") as fh:
            resp = await self.client.audio.transcriptions.create(
                model=self.s.stt_model, file=fh, response_format="json"
            )
        text = getattr(resp, "text", "") or ""
        dur = max(30.0, len(text.split()) / 2.4)
        return text, dur


class OpenAITTS:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.client = _client(settings)

    async def synthesize(self, text: str, voice_id: str, out_path: str) -> float:
        # OpenAI TTS returns mp3/wav bytes; we request wav for the stdlib mixer.
        try:
            resp = await self.client.audio.speech.create(
                model=self.s.tts_model,
                voice=_openai_voice(voice_id),
                input=text[:4000] or "…",
                response_format="wav",
            )
            data = resp.read() if hasattr(resp, "read") else resp.content
            with open(out_path, "wb") as f:
                f.write(data)
            import wave

            with wave.open(out_path, "r") as w:
                return w.getnframes() / w.getframerate()
        except Exception:
            return write_wav(out_path, _mock_speak(text, voice_id))


# OpenAI has a fixed voice set; map our persona/character voice ids onto it.
_OPENAI_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer", "coral", "sage"]


def _openai_voice(voice_id: str) -> str:
    return _OPENAI_VOICES[sum(ord(c) for c in voice_id) % len(_OPENAI_VOICES)]
