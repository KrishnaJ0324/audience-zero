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
from ..contracts import (
    Beat,
    BeatScore,
    CharacterProfile,
    CharacterState,
    ConsistencyIssue,
    Episode,
    MemorySpec,
    PersonaConfig,
    PersonaReport,
    RevisedScene,
    StoryAdvance,
)
from ..services import verdict_engine  # skip_index only; verdict_engine imports no providers
from . import heuristics
from .mock import MockLLM, MockTTS
from .wavtools import write_wav
from .wavtools import speak as _mock_speak


def _client(settings: Settings):
    from openai import AsyncOpenAI

    # base_url is set only when pointing at an OpenAI-compatible gateway (e.g.
    # Databricks Foundation Model APIs at /serving-endpoints); otherwise the SDK
    # default applies. Model names must match that gateway's served endpoints.
    kwargs: dict = {"api_key": settings.effective_openai_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return AsyncOpenAI(**kwargs)


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
            "sentence, in your voice, said aloud.\n"
            f"beat_index and skip_at_beat are ZERO-BASED indices in "
            f"[0, {len(beats) - 1}] — they are the [Beat N] labels below, NOT "
            "1-based positions. skip_at_beat is the beat where you stopped "
            "listening, or null if you finished."
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
            # scores are filtered against `valid` above; skip_at_beat was not,
            # so a 1-based answer (== len(beats)) used to match no beat and the
            # listener's churn vanished. Clamp it onto a real index instead.
            raw_skip = data.get("skip_at_beat")
            try:
                skip = verdict_engine.skip_index(
                    None if raw_skip is None else int(raw_skip), len(beats)
                )
            except (TypeError, ValueError):
                skip = None
            return PersonaReport(
                persona_id=persona.id,
                scores=sorted(scores, key=lambda s: s.beat_index),
                skip_at_beat=skip,
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

    async def extract_character_state(
        self, prior_states: dict[str, CharacterState], beat_text: str
    ) -> dict[str, CharacterState]:
        sys = (
            "You maintain a character-state ledger for a serialized story. Given "
            "the prior ledger and one ALREADY-WRITTEN beat of text, update it: add "
            "any new memory facts, refine emotional_state, and relationships "
            "between characters who appear together. Do NOT invent events beyond "
            "what the beat text says. Return STRICT JSON: {\"states\": "
            "{name: {\"memory\": [str], \"emotional_state\": str, "
            "\"relationships\": {other_name: str}}}}."
        )
        user = (
            f"PRIOR LEDGER:\n{json.dumps({k: v.model_dump() for k, v in prior_states.items()})}"
            f"\n\nBEAT TEXT:\n{beat_text}"
        )
        try:
            resp = await self.client.chat.completions.create(
                model=self.s.consistency_model,
                messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            states = data.get("states", {})
            if not isinstance(states, dict):
                raise ValueError("malformed ledger")
            return {
                name: CharacterState(
                    name=name,
                    memory=list(v.get("memory", []))[-8:],
                    emotional_state=str(v.get("emotional_state", "neutral")),
                    relationships=dict(v.get("relationships", {})),
                )
                for name, v in states.items()
            }
        except Exception:
            return await MockLLM().extract_character_state(prior_states, beat_text)

    async def advance_story(
        self, prior_states: dict[str, CharacterState], context_text: str, instruction: str
    ) -> StoryAdvance:
        sys = (
            "You are a story co-writer. Continue the scene per the user's "
            "free-form instruction, staying consistent with the given character "
            "ledger and recent context. Write ONE new scene (dialogue + light "
            "narration), not a summary. In the SAME response, update the "
            "character ledger for anyone who appears. Return STRICT JSON: "
            "{\"text\": str, \"summary\": str, \"character_states\": "
            "{name: {\"memory\": [str], \"emotional_state\": str, "
            "\"relationships\": {other_name: str}}}}."
        )
        user = (
            f"CHARACTER LEDGER:\n{json.dumps({k: v.model_dump() for k, v in prior_states.items()})}"
            f"\n\nRECENT CONTEXT:\n{context_text}\n\nINSTRUCTION:\n{instruction}"
        )
        try:
            resp = await self.client.chat.completions.create(
                model=self.s.continuation_model,
                messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                temperature=0.85,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            text = str(data.get("text", "")).strip()
            if not text:
                raise ValueError("empty continuation")
            states = data.get("character_states", {})
            character_states = {
                name: CharacterState(
                    name=name,
                    memory=list(v.get("memory", []))[-8:],
                    emotional_state=str(v.get("emotional_state", "neutral")),
                    relationships=dict(v.get("relationships", {})),
                )
                for name, v in states.items()
            } if isinstance(states, dict) else {}
            return StoryAdvance(
                text=text, character_states=character_states,
                summary=str(data.get("summary", ""))[:120],
            )
        except Exception:
            return await MockLLM().advance_story(prior_states, context_text, instruction)

    async def check_consistency(
        self,
        established_states: dict[str, CharacterState],
        ancestor_summaries: list[str],
        new_text: str,
        new_states: dict[str, CharacterState],
    ) -> list[ConsistencyIssue]:
        sys = (
            "You are a continuity checker for a branching story. Compare the new "
            "scene + its inferred character states against the established ledger "
            "and prior beat summaries. Flag ONLY genuine contradictions (a "
            "character doing/feeling something that directly conflicts with an "
            "established fact) — do not flag plausible new developments. Return "
            "STRICT JSON: {\"issues\": [{\"severity\": \"info\"|\"warning\"|"
            "\"critical\", \"summary\": str, \"conflicting_fact\": str, "
            "\"character\": str}]}. Empty list if nothing contradicts."
        )
        user = (
            f"ESTABLISHED LEDGER:\n{json.dumps({k: v.model_dump() for k, v in established_states.items()})}"
            f"\n\nPRIOR SUMMARIES:\n{ancestor_summaries}"
            f"\n\nNEW SCENE:\n{new_text}"
            f"\n\nNEW LEDGER:\n{json.dumps({k: v.model_dump() for k, v in new_states.items()})}"
        )
        try:
            resp = await self.client.chat.completions.create(
                model=self.s.consistency_model,
                messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            raw = data.get("issues", [])
            if not isinstance(raw, list):
                raise ValueError("malformed issues")
            return [
                ConsistencyIssue(
                    id=f"ci_{heuristics.stable_seed(str(i), new_text[:40]):08x}",
                    severity=iss.get("severity", "warning"),
                    summary=str(iss.get("summary", ""))[:280],
                    conflicting_fact=str(iss.get("conflicting_fact", ""))[:200],
                    character=str(iss.get("character", "")),
                )
                for i, iss in enumerate(raw)
            ]
        except Exception:
            return await MockLLM().check_consistency(
                established_states, ancestor_summaries, new_text, new_states)

    async def generate_memory(
        self,
        parent_spec: MemorySpec | None,
        episode_text: str,
        prior_states: dict[str, CharacterState],
    ) -> MemorySpec:
        sys = (
            "You maintain a story bible for a serialized story. Given the "
            "parent version's story bible (if any) and this version's episode "
            "text, produce an updated bible: theme, each character's role and "
            "behavior notes, and cross-cutting constraints future episodes "
            "must respect. Preserve continuity from the parent bible; only add "
            "or refine, never contradict it without reason. Return STRICT "
            "JSON: {\"theme\": str, \"characters\": [{\"name\": str, "
            "\"role\": str, \"behavior_notes\": str}], \"constraints\": [str]}."
        )
        user = (
            f"PARENT BIBLE:\n{parent_spec.model_dump_json() if parent_spec else '(none — this is the root episode)'}"
            f"\n\nCHARACTER LEDGER:\n{json.dumps({k: v.model_dump() for k, v in prior_states.items()})}"
            f"\n\nEPISODE TEXT:\n{episode_text}"
        )
        try:
            resp = await self.client.chat.completions.create(
                model=self.s.memory_model,
                messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            characters = [
                CharacterProfile(
                    name=str(c.get("name", "")), role=str(c.get("role", "")),
                    behavior_notes=str(c.get("behavior_notes", "")),
                )
                for c in data.get("characters", []) if c.get("name")
            ]
            constraints = [str(c) for c in data.get("constraints", [])][:12]
            theme = str(data.get("theme", "")) or (parent_spec.theme if parent_spec else "")
            if not theme and not characters:
                raise ValueError("empty story bible")
            return MemorySpec(theme=theme, characters=characters[:12], constraints=constraints)
        except Exception:
            return await MockLLM().generate_memory(parent_spec, episode_text, prior_states)


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
