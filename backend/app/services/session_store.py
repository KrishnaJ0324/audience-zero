"""Session Store (§2.3 component 9) — v2 producer-workflow hierarchy.

Persists Project -> Episode -> Version -> AnalysisRun, plus read-only share
tokens and uploaded 'actual' retention, to SQLite. One file, zero ops, survives
restarts (cached demo replays instantly). Rich Pydantic objects are stored as
JSON blobs keyed by id; a few columns are denormalised for cheap listing.

The dev DB is disposable — this schema is created fresh; there is no migration
from the v1 (episodes+runs) shape. Re-seed with ``scripts/seed_demo.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from ..contracts import AnalysisRun, EpisodeMeta, PersonaConfig, Project, StoryNode, Universe, Version

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, name TEXT, created_at TEXT, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY, project_id TEXT, title TEXT, created_at TEXT, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS versions (
    id TEXT PRIMARY KEY, episode_id TEXT, project_id TEXT, label TEXT,
    parent_version_id TEXT, universe_id TEXT, created_at TEXT, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS universes (
    id TEXT PRIMARY KEY, project_id TEXT, name TEXT, created_at TEXT, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, version_id TEXT, episode_id TEXT, project_id TEXT,
    parent_run_id TEXT, status TEXT, created_at TEXT, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shares (
    token TEXT PRIMARY KEY, run_id TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS actuals (
    episode_id TEXT PRIMARY KEY, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS custom_personas (
    id TEXT PRIMARY KEY, name TEXT, created_at TEXT, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_persona_state (
    project_id TEXT, persona_id TEXT, enabled INTEGER NOT NULL,
    PRIMARY KEY (project_id, persona_id)
);
CREATE TABLE IF NOT EXISTS story_nodes (
    id TEXT PRIMARY KEY, root_version_id TEXT, episode_id TEXT, project_id TEXT,
    parent_node_id TEXT, created_at TEXT, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_episodes_project ON episodes(project_id);
CREATE INDEX IF NOT EXISTS idx_versions_episode ON versions(episode_id);
CREATE INDEX IF NOT EXISTS idx_runs_version ON runs(version_id);
CREATE INDEX IF NOT EXISTS idx_runs_episode ON runs(episode_id);
CREATE INDEX IF NOT EXISTS idx_nodes_root ON story_nodes(root_version_id);
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON story_nodes(parent_node_id);
CREATE INDEX IF NOT EXISTS idx_universes_project ON universes(project_id);
"""


class SessionStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            # additive migration: a pre-existing dev DB from before universes
            # existed won't have this column yet (CREATE TABLE IF NOT EXISTS
            # never adds columns to an already-existing table).
            async with db.execute("PRAGMA table_info(versions)") as cur:
                cols = {row[1] for row in await cur.fetchall()}
            if "universe_id" not in cols:
                await db.execute("ALTER TABLE versions ADD COLUMN universe_id TEXT")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_versions_universe ON versions(universe_id)"
            )
            await db.commit()

    # --- projects -------------------------------------------------------
    async def save_project(self, p: Project) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO projects (id, name, created_at, data) VALUES (?,?,?,?)",
                (p.id, p.name, p.created_at, p.model_dump_json()),
            )
            await db.commit()

    async def get_project(self, project_id: str) -> Project | None:
        row = await self._one("SELECT data FROM projects WHERE id=?", (project_id,))
        return Project.model_validate_json(row[0]) if row else None

    async def list_projects(self, limit: int = 100) -> list[Project]:
        rows = await self._all(
            "SELECT data FROM projects ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [Project.model_validate_json(r[0]) for r in rows]

    # --- episodes (logical) --------------------------------------------
    async def save_episode(self, e: EpisodeMeta) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO episodes (id, project_id, title, created_at, data)"
                " VALUES (?,?,?,?,?)",
                (e.id, e.project_id, e.title, e.created_at, e.model_dump_json()),
            )
            await db.commit()

    async def get_episode(self, episode_id: str) -> EpisodeMeta | None:
        row = await self._one("SELECT data FROM episodes WHERE id=?", (episode_id,))
        return EpisodeMeta.model_validate_json(row[0]) if row else None

    async def list_episodes(self, project_id: str) -> list[EpisodeMeta]:
        rows = await self._all(
            "SELECT data FROM episodes WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        )
        return [EpisodeMeta.model_validate_json(r[0]) for r in rows]

    # --- versions -------------------------------------------------------
    async def save_version(self, v: Version) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO versions"
                " (id, episode_id, project_id, label, parent_version_id, universe_id, created_at, data)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (v.id, v.episode_id, v.project_id, v.label, v.parent_version_id,
                 v.universe_id, v.created_at, v.model_dump_json()),
            )
            await db.commit()

    async def get_version(self, version_id: str) -> Version | None:
        row = await self._one("SELECT data FROM versions WHERE id=?", (version_id,))
        return Version.model_validate_json(row[0]) if row else None

    async def list_versions(self, episode_id: str) -> list[Version]:
        rows = await self._all(
            "SELECT data FROM versions WHERE episode_id=? ORDER BY created_at ASC",
            (episode_id,),
        )
        return [Version.model_validate_json(r[0]) for r in rows]

    async def list_versions_by_universe(self, universe_id: str) -> list[Version]:
        rows = await self._all(
            "SELECT data FROM versions WHERE universe_id=? ORDER BY created_at ASC",
            (universe_id,),
        )
        return [Version.model_validate_json(r[0]) for r in rows]

    async def list_all_versions_for_project(self, project_id: str) -> list[Version]:
        rows = await self._all(
            "SELECT data FROM versions WHERE project_id=? ORDER BY created_at ASC",
            (project_id,),
        )
        return [Version.model_validate_json(r[0]) for r in rows]

    # --- universes (parallel timelines across episodes) ------------------
    async def save_universe(self, u: Universe) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO universes (id, project_id, name, created_at, data)"
                " VALUES (?,?,?,?,?)",
                (u.id, u.project_id, u.name, u.created_at, u.model_dump_json()),
            )
            await db.commit()

    async def get_universe(self, universe_id: str) -> Universe | None:
        row = await self._one("SELECT data FROM universes WHERE id=?", (universe_id,))
        return Universe.model_validate_json(row[0]) if row else None

    async def list_universes(self, project_id: str) -> list[Universe]:
        rows = await self._all(
            "SELECT data FROM universes WHERE project_id=? ORDER BY created_at ASC",
            (project_id,),
        )
        return [Universe.model_validate_json(r[0]) for r in rows]

    # --- runs -----------------------------------------------------------
    async def save_run(self, run: AnalysisRun) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO runs"
                " (id, version_id, episode_id, project_id, parent_run_id, status, created_at, data)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (run.id, run.version_id, run.episode_id, run.project_id, run.parent_run_id,
                 run.status, run.created_at, run.model_dump_json()),
            )
            await db.commit()

    async def get_run(self, run_id: str) -> AnalysisRun | None:
        row = await self._one("SELECT data FROM runs WHERE id=?", (run_id,))
        return AnalysisRun.model_validate_json(row[0]) if row else None

    async def list_runs(self, limit: int = 50) -> list[AnalysisRun]:
        rows = await self._all(
            "SELECT data FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [AnalysisRun.model_validate_json(r[0]) for r in rows]

    async def list_runs_for_episode(self, episode_id: str) -> list[AnalysisRun]:
        rows = await self._all(
            "SELECT data FROM runs WHERE episode_id=? ORDER BY created_at DESC",
            (episode_id,),
        )
        return [AnalysisRun.model_validate_json(r[0]) for r in rows]

    # --- story nodes (time-travel branching) -----------------------------
    async def save_node(self, n: StoryNode) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO story_nodes"
                " (id, root_version_id, episode_id, project_id, parent_node_id, created_at, data)"
                " VALUES (?,?,?,?,?,?,?)",
                (n.id, n.root_version_id, n.episode_id, n.project_id, n.parent_node_id,
                 n.created_at, n.model_dump_json()),
            )
            await db.commit()

    async def get_node(self, node_id: str) -> StoryNode | None:
        row = await self._one("SELECT data FROM story_nodes WHERE id=?", (node_id,))
        return StoryNode.model_validate_json(row[0]) if row else None

    async def list_nodes_for_version(self, root_version_id: str) -> list[StoryNode]:
        rows = await self._all(
            "SELECT data FROM story_nodes WHERE root_version_id=? ORDER BY created_at ASC",
            (root_version_id,),
        )
        return [StoryNode.model_validate_json(r[0]) for r in rows]

    # --- shares ---------------------------------------------------------
    async def save_share(self, token: str, run_id: str, created_at: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO shares (token, run_id, created_at) VALUES (?,?,?)",
                (token, run_id, created_at),
            )
            await db.commit()

    async def get_share(self, token: str) -> str | None:
        row = await self._one("SELECT run_id FROM shares WHERE token=?", (token,))
        return row[0] if row else None

    # --- actuals (real retention for calibration) ----------------------
    async def save_actual(self, episode_id: str, retention: list[float]) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO actuals (episode_id, data) VALUES (?,?)",
                (episode_id, json.dumps(retention)),
            )
            await db.commit()

    async def get_actual(self, episode_id: str) -> list[float] | None:
        row = await self._one("SELECT data FROM actuals WHERE episode_id=?", (episode_id,))
        return json.loads(row[0]) if row else None

    # --- custom personas -----------------------------------------------
    async def save_persona(self, p: PersonaConfig) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO custom_personas (id, name, created_at, data) VALUES (?,?,?,?)",
                (p.id, p.name, p.created_at, p.model_dump_json()),
            )
            await db.commit()

    async def list_personas(self) -> list[PersonaConfig]:
        rows = await self._all("SELECT data FROM custom_personas ORDER BY created_at ASC", ())
        return [PersonaConfig.model_validate_json(r[0]) for r in rows]

    async def get_persona(self, persona_id: str) -> PersonaConfig | None:
        row = await self._one("SELECT data FROM custom_personas WHERE id=?", (persona_id,))
        return PersonaConfig.model_validate_json(row[0]) if row else None

    async def delete_persona(self, persona_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM custom_personas WHERE id=?", (persona_id,))
            await db.execute("DELETE FROM project_persona_state WHERE persona_id=?", (persona_id,))
            await db.commit()

    # --- per-project persona enable/disable state ----------------------
    async def set_project_persona_enabled(self, project_id: str, persona_id: str, enabled: bool) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO project_persona_state (project_id, persona_id, enabled)"
                " VALUES (?,?,?)",
                (project_id, persona_id, 1 if enabled else 0),
            )
            await db.commit()

    async def project_persona_states(self, project_id: str) -> dict[str, bool]:
        rows = await self._all(
            "SELECT persona_id, enabled FROM project_persona_state WHERE project_id=?",
            (project_id,),
        )
        return {r[0]: bool(r[1]) for r in rows}

    # --- helpers --------------------------------------------------------
    async def _one(self, sql: str, args: tuple):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(sql, args) as cur:
                return await cur.fetchone()

    async def _all(self, sql: str, args: tuple):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(sql, args) as cur:
                return await cur.fetchall()
