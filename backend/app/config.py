"""Runtime configuration.

Every external dependency sits behind an interface (design principle #5). The
single most important knob here is ``provider``: with ``mock`` the entire golden
path runs deterministically and offline (no API key, no network, no ffmpeg). With
``openai`` the real adapters are used. If ``auto`` (default) we pick ``openai``
only when an API key is present, otherwise ``mock``.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_prefix="AZ_",
        extra="ignore",
    )

    # --- providers ------------------------------------------------------
    provider: Literal["auto", "mock", "openai"] = "auto"
    openai_api_key: str | None = None

    # OpenAI model defaults (per-persona models still win when configured)
    stt_model: str = "gpt-4o-transcribe"
    segmenter_model: str = "gpt-4o-mini"
    revision_model: str = "gpt-4o"
    default_persona_model: str = "gpt-4o-mini"
    tts_model: str = "gpt-4o-mini-tts"

    # --- paths ----------------------------------------------------------
    personas_dir: Path = BACKEND_ROOT / "personas"
    scripts_dir: Path = BACKEND_ROOT / "data" / "scripts"
    audio_dir: Path = BACKEND_ROOT / "data" / "audio"
    db_path: Path = BACKEND_ROOT / "data" / "audience_zero.db"

    # --- orchestration --------------------------------------------------
    per_agent_timeout_s: float = 60.0
    per_agent_retries: int = 1
    # theatre pacing: delay (seconds) between beat_scored events so the UI can
    # animate progressively. Computation is real; streaming is theatre (#4).
    reveal_delay_s: float = 0.18

    # --- segmentation ---------------------------------------------------
    min_beats: int = 10
    max_beats: int = 15

    # --- server ---------------------------------------------------------
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def resolved_provider(self) -> Literal["mock", "openai"]:
        key = self.openai_api_key or os.getenv("OPENAI_API_KEY")
        if self.provider == "openai":
            return "openai"
        if self.provider == "mock":
            return "mock"
        return "openai" if key else "mock"

    @property
    def effective_openai_key(self) -> str | None:
        return self.openai_api_key or os.getenv("OPENAI_API_KEY")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.audio_dir.mkdir(parents=True, exist_ok=True)
    s.db_path.parent.mkdir(parents=True, exist_ok=True)
    return s
