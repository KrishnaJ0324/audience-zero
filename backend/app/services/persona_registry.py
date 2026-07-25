"""Persona Registry (§2.3 component 3).

Personas are data, not code (design principle #2). Loads and schema-validates
``personas/*.yaml``. Adding persona #7–12 later = adding a file; the
orchestrator never learns persona internals.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..config import get_settings
from ..contracts import PersonaConfig


class PersonaRegistry:
    def __init__(self, personas_dir: Path | None = None) -> None:
        self.dir = personas_dir or get_settings().personas_dir
        self._cache: list[PersonaConfig] | None = None

    def load(self, force: bool = False) -> list[PersonaConfig]:
        if self._cache is not None and not force:
            return self._cache
        configs: list[PersonaConfig] = []
        for path in sorted(self.dir.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            configs.append(PersonaConfig(**raw))
        if not configs:
            raise RuntimeError(f"No persona configs found in {self.dir}")
        ids = [c.id for c in configs]
        if len(ids) != len(set(ids)):
            raise RuntimeError(f"Duplicate persona ids: {ids}")
        self._cache = configs
        return configs

    def get(self, persona_id: str) -> PersonaConfig | None:
        return next((p for p in self.load() if p.id == persona_id), None)
