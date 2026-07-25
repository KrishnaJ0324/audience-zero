"""Session Store (§2.3 component 9).

Persists episodes and runs to SQLite — one file, zero ops, survives process
restarts (so a cached demo run replays instantly). Enables re-run comparison
and instant replay. Stores the rich Pydantic objects as JSON blobs keyed by id.
"""
from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from ..contracts import Episode, PanelRun

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TEXT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    episode_id TEXT,
    parent_run_id TEXT,
    status TEXT,
    created_at TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_episode ON runs(episode_id);
"""


class SessionStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    # --- episodes -------------------------------------------------------
    async def save_episode(self, ep: Episode) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO episodes (id, title, created_at, data) VALUES (?,?,?,?)",
                (ep.id, ep.title, "", ep.model_dump_json()),
            )
            await db.commit()

    async def get_episode(self, episode_id: str) -> Episode | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT data FROM episodes WHERE id=?", (episode_id,)) as cur:
                row = await cur.fetchone()
        return Episode.model_validate_json(row[0]) if row else None

    # --- runs -----------------------------------------------------------
    async def save_run(self, run: PanelRun) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO runs (id, episode_id, parent_run_id, status, created_at, data)"
                " VALUES (?,?,?,?,?,?)",
                (run.id, run.episode_id, run.parent_run_id, run.status, run.created_at,
                 run.model_dump_json()),
            )
            await db.commit()

    async def get_run(self, run_id: str) -> PanelRun | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT data FROM runs WHERE id=?", (run_id,)) as cur:
                row = await cur.fetchone()
        return PanelRun.model_validate_json(row[0]) if row else None

    async def list_runs(self, limit: int = 50) -> list[PanelRun]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT data FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cur:
                rows = await cur.fetchall()
        return [PanelRun.model_validate_json(r[0]) for r in rows]
