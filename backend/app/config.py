"""Runtime configuration.

Every external dependency sits behind an interface (design principle #5). The
single most important knob here is ``provider``: with ``mock`` the entire golden
path runs deterministically and offline (no API key, no network, no ffmpeg). With
``openai`` the real adapters are used. If ``auto`` (default) we pick ``openai``
only when an API key is present, otherwise ``mock``.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_prefix="AZ_",
        extra="ignore",
        # fields carrying a validation_alias (cors_origins_raw) would otherwise
        # be unsettable by their Python name, including from tests
        populate_by_name=True,
    )

    # --- providers ------------------------------------------------------
    provider: Literal["auto", "mock", "openai"] = "auto"
    openai_api_key: str | None = None
    # Optional OpenAI-compatible base URL. Databricks Foundation Model APIs are
    # callable with the OpenAI client, so on a Free Edition workspace the same
    # adapter runs against `https://<host>/serving-endpoints` with a Databricks
    # token — no external OpenAI key and no external spend. Unset => api.openai.com.
    openai_base_url: str | None = None

    # OpenAI model defaults (per-persona models still win when configured)
    stt_model: str = "gpt-4o-transcribe"
    segmenter_model: str = "gpt-4o-mini"
    revision_model: str = "gpt-4o"
    default_persona_model: str = "gpt-4o-mini"
    tts_model: str = "gpt-4o-mini-tts"
    continuation_model: str = "gpt-4o"        # advance_story — real generation
    consistency_model: str = "gpt-4o-mini"    # extract_character_state + check_consistency
    memory_model: str = "gpt-4o-mini"         # generate_memory — story-bible spec extraction

    # --- story tree -------------------------------------------------------
    story_context_window: int = 3  # full-text ancestors before falling back to summaries

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
    # Kept as a raw string on purpose. pydantic-settings decodes a `list[str]`
    # env var as JSON *inside the settings source*, before any validator runs —
    # so `AZ_CORS_ORIGINS=https://app.example.com` raised SettingsError and the
    # whole service refused to boot. A CORS typo must not be able to take the
    # API down, so parsing happens in `cors_origins` below instead.
    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        # validation_alias bypasses env_prefix, so this is the full env name.
        validation_alias="AZ_CORS_ORIGINS",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Allowed browser origins, from a JSON array, a comma-separated list,
        or a single bare origin — whichever the operator happened to type.

        Trailing slashes are stripped because CORS compares the `Origin` header
        exactly, and `https://app.example.com/` never matches a real origin.
        """
        raw = (self.cors_origins_raw or "").strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                loaded = json.loads(raw)
                items = [str(x) for x in loaded] if isinstance(loaded, list) else [raw]
            except ValueError:
                # malformed array (e.g. a missing quote) — salvage it rather
                # than refusing to start
                items = raw.strip("[]").split(",")
        else:
            items = raw.split(",")
        out: list[str] = []
        for item in items:
            origin = item.strip().strip('"').strip("'").rstrip("/")
            if origin and origin not in out:
                out.append(origin)
        return out

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
