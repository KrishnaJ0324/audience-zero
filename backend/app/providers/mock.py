"""Deterministic, offline provider implementations.

No network, no API key, no ffmpeg. This is what makes the project a *properly
working* build out of the box and keeps the demo bulletproof (§2.8 — if wifi
dies the whole golden path still runs).
"""
from __future__ import annotations

import re

from ..contracts import Beat, Episode, PersonaConfig, PersonaReport, RevisedScene
from . import heuristics, wavtools

_BEAT_MARKER = re.compile(r"(?im)^\s*(?:#+\s*)?(?:beat|scene)\s*\d+\b.*$")


class MockLLM:
    """Segments, judges (via heuristics) and revises — all deterministic."""

    async def segment(self, transcript: str, min_beats: int, max_beats: int) -> list[Beat]:
        chunks = self._split(transcript, min_beats, max_beats)
        # synthesise an even timeline; ingestion overrides for real audio.
        total = max(len(transcript.split()) / 2.4, 60.0)  # ~2.4 wps reading pace
        per = total / len(chunks)
        beats: list[Beat] = []
        for i, ch in enumerate(chunks):
            beats.append(
                Beat(
                    index=i,
                    start_s=round(i * per, 2),
                    end_s=round((i + 1) * per, 2),
                    summary=self._summary(ch),
                    text=ch.strip(),
                )
            )
        return beats

    @staticmethod
    def _split(transcript: str, min_beats: int, max_beats: int) -> list[str]:
        text = transcript.strip()
        # 1) explicit BEAT/SCENE markers win
        markers = list(_BEAT_MARKER.finditer(text))
        if len(markers) >= min_beats - 2:
            chunks, starts = [], [m.start() for m in markers] + [len(text)]
            for a, b in zip(starts, starts[1:]):
                seg = text[a:b].strip()
                if seg:
                    chunks.append(seg)
            if chunks:
                return chunks[:max_beats]
        # 2) blank-line paragraphs
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if len(paras) >= min_beats:
            return MockLLM._rebalance(paras, min_beats, max_beats)
        # 3) fall back to sentence packing
        sents = re.split(r"(?<=[.!?])\s+", text)
        sents = [s for s in sents if s.strip()]
        target = max(min_beats, min(max_beats, max(len(sents) // 3, min_beats)))
        return MockLLM._pack(sents, target)

    @staticmethod
    def _rebalance(paras: list[str], min_beats: int, max_beats: int) -> list[str]:
        if len(paras) <= max_beats:
            return paras
        return MockLLM._pack(paras, max_beats)

    @staticmethod
    def _pack(items: list[str], target: int) -> list[str]:
        if target <= 0 or not items:
            return items or [""]
        size = max(1, round(len(items) / target))
        out = [" ".join(items[i : i + size]) for i in range(0, len(items), size)]
        return out[:target] if len(out) > target else out

    @staticmethod
    def _summary(chunk: str) -> str:
        first = re.sub(r"(?im)^\s*(?:#+\s*)?(?:beat|scene)\s*\d+[:.\-]?\s*", "", chunk).strip()
        first = re.split(r"(?<=[.!?])\s", first)[0]
        return (first[:90] + "…") if len(first) > 90 else first or "(scene)"

    async def evaluate(
        self, episode: Episode, beats: list[Beat], persona: PersonaConfig
    ) -> PersonaReport:
        return heuristics.make_report(persona, episode, beats)

    async def revise(
        self, beat: Beat, critiques: list[str], speakers: list[str]
    ) -> RevisedScene:
        crit = " ".join(critiques).lower()
        original = beat.text
        # deterministic edit: strip recap, inject a hook + a tension beat,
        # thin the cast to <=3 speakers.
        lines = [ln for ln in original.splitlines() if ln.strip()]
        kept = []
        for ln in lines:
            low = ln.lower()
            if any(k in low for k in heuristics.RECAP):
                continue  # cut recap
            kept.append(ln)
        # Guarantee a genuinely multi-voice scene (multi-voice + music + SFX is
        # the product promise). If the flagged beat was narrator-only, cast two
        # named leads so the produced audio has distinct voices.
        speaker_list = list(dict.fromkeys(s for s in speakers if s.upper() != "NARRATOR"))
        for fallback in ("MAYA", "DEV", "RIAA"):
            if len(speaker_list) >= 2:
                break
            if fallback not in speaker_list:
                speaker_list.append(fallback)
        speaker_list = speaker_list[:3]
        a, b = speaker_list[0], speaker_list[1]

        ending_mode = "ending" in crit or "stronger hook" in crit
        if ending_mode:
            # Strengthen-ending: KEEP the original beat and escalate the closing
            # hook so the final-beat engagement (and thus Binge Probability) can
            # only rise — never truncate an already-strong cliffhanger.
            stinger = [
                f"{a}: (a whisper) There's one more thing you were never meant to hear.",
                "NARRATOR: But then — the unknown number calls again.",
                "NARRATOR: Who was really in the coffin? To be continued. What happens next?",
                "SFX: a phone rings in the dark. Don't hang up.",
            ]
            new_text = original.rstrip() + "\n" + "\n".join(stinger)
            rationale = (
                "Kept the beat intact and escalated the closing hook — a sharper "
                "cliffhanger and an unanswered question that drives the press on "
                "the next episode (higher binge probability)."
            )
            casting = {sp: sp.lower().split()[0] for sp in speaker_list}
            return RevisedScene(
                beat_index=beat.index,
                new_text=new_text,
                change_rationale=rationale,
                casting=casting,
            )

        rewrite = []
        rewrite.append(f"{a}: (low, urgent) We don't have time to go over this again.")
        rewrite.append(f"{b}: Then say the part you've been afraid to say.")
        rewrite.extend(kept[:4])
        if "no_hook" in crit or "hook" in crit or not crit:
            rewrite.append(f"{a}: (a beat) ...There's one thing I never told you.")
            rewrite.append("SFX: a phone buzzes. Unknown number.")
        new_text = "\n".join(rewrite)
        rationale = (
            "Cut the recap the panel flagged, tightened the cast to three voices, "
            "raised the stakes mid-scene, and planted a closing hook so the beat "
            "pulls listeners forward instead of stalling."
        )
        casting = {sp: sp.lower().split()[0] for sp in speaker_list}
        return RevisedScene(
            beat_index=beat.index,
            new_text=new_text,
            change_rationale=rationale,
            casting=casting,
        )


class MockSTT:
    async def transcribe(self, audio_bytes: bytes, filename: str) -> tuple[str, float]:
        # We can't really decode arbitrary audio offline; return a canned
        # transcript so the audio-input path is demonstrable without a key.
        dur = max(30.0, min(len(audio_bytes) / 32000.0, 240.0))
        transcript = (
            "BEAT 1: Cold open on a rooftop at dawn.\n\n"
            "BEAT 2: The two leads argue about the missing tape.\n\n"
            "BEAT 3: A long recap of everything that happened last episode.\n\n"
            "BEAT 4: They finally find the locker; it's empty.\n\n"
            "BEAT 5: A stranger calls. 'You're looking in the wrong place.'"
        )
        return transcript, dur


class MockTTS:
    async def synthesize(self, text: str, voice_id: str, out_path: str) -> float:
        samples = wavtools.speak(text, voice_id)
        return wavtools.write_wav(out_path, samples)


class MockMixer:
    async def mix(
        self, line_clips: list[str], out_path: str, music: bool = True, sfx: bool = False
    ) -> float:
        import wave as _wave

        line_samples: list[list[float]] = []
        for clip in line_clips:
            with _wave.open(clip, "r") as w:
                n = w.getnframes()
                raw = w.readframes(n)
            import struct as _struct

            vals = list(_struct.unpack("<" + "h" * (len(raw) // 2), raw))
            line_samples.append([v / 32767.0 for v in vals])
        track = wavtools.compose_scene(line_samples, music=music, sfx=sfx)
        return wavtools.write_wav(out_path, track)
