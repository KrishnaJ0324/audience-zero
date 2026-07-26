"""Isolate every test from the real dev database and audio directory.

``get_settings()`` is an lru_cache'd singleton, and it defaults ``db_path``/
``audio_dir`` to ``backend/data/...`` — the SAME files the live dev server
reads from. Without this fixture, every pytest run silently writes fixture
projects (and any produced audio) straight into the shared dev database.
"""
from __future__ import annotations

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path):
    s = get_settings()
    s.db_path = tmp_path / "test_audience_zero.db"
    s.audio_dir = tmp_path / "audio"
    s.audio_dir.mkdir(parents=True, exist_ok=True)
