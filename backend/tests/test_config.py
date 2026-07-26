"""Config parsing regressions.

`AZ_CORS_ORIGINS` is boot-critical: it is read at import time in main.py, so a
malformed value doesn't degrade the API — it prevents the process from starting
at all. It did exactly that in production once, because pydantic-settings
decodes `list[str]` env vars as JSON inside the settings source (before any
validator runs), and the natural thing to type is a bare URL.
"""
from __future__ import annotations

import pytest

from app.config import Settings


def _origins(raw: str | None) -> list[str]:
    return Settings(**({"cors_origins_raw": raw} if raw is not None else {})).cors_origins


def test_default_allows_local_dev():
    assert _origins(None) == ["http://localhost:5173", "http://127.0.0.1:5173"]


@pytest.mark.parametrize(
    "raw",
    [
        "https://audience-zero.netlify.app",                      # bare origin
        "https://audience-zero.netlify.app/",                     # pasted from a browser bar
        '["https://audience-zero.netlify.app"]',                  # JSON array
        '  ["https://audience-zero.netlify.app"]  ',              # padded
        '["https://audience-zero.netlify.app]',                   # malformed: missing quote
        "'https://audience-zero.netlify.app'",                    # stray quotes
    ],
)
def test_every_plausible_spelling_yields_the_same_origin(raw):
    """None of these may raise, and all mean the same thing."""
    assert _origins(raw) == ["https://audience-zero.netlify.app"]


@pytest.mark.parametrize(
    "raw",
    [
        '["https://a.example.com","http://localhost:5173"]',
        "https://a.example.com,http://localhost:5173",
        "https://a.example.com/ , http://localhost:5173/",
    ],
)
def test_multiple_origins(raw):
    assert _origins(raw) == ["https://a.example.com", "http://localhost:5173"]


def test_empty_disables_cors_without_crashing():
    assert _origins("") == []


def test_duplicates_collapse():
    assert _origins("https://a.example.com,https://a.example.com/") == ["https://a.example.com"]
