"""Chooses concrete providers from settings. The mixer is always the stdlib
WAV mixer (no ffmpeg dependency); STT/TTS/LLM switch between mock and OpenAI."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings, get_settings
from . import mock
from .base import AudioMixer, LLMJudge, STTProvider, TTSProvider


@dataclass
class Providers:
    llm: LLMJudge
    stt: STTProvider
    tts: TTSProvider
    mixer: AudioMixer
    kind: str


def build_providers(settings: Settings | None = None) -> Providers:
    s = settings or get_settings()
    mixer = mock.MockMixer()  # stdlib WAV mixing, works everywhere
    if s.resolved_provider == "openai":
        from . import openai_provider as oa

        return Providers(
            llm=oa.OpenAILLM(s),
            stt=oa.OpenAISTT(s),
            tts=oa.OpenAITTS(s),
            mixer=mixer,
            kind="openai",
        )
    return Providers(
        llm=mock.MockLLM(),
        stt=mock.MockSTT(),
        tts=mock.MockTTS(),
        mixer=mixer,
        kind="mock",
    )
