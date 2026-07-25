"""Persona Agent Runtime (§2.3 component 5).

One agent = one call to its own configured model with its own system prompt.
Internals are opaque to the orchestrator; it only ever gets a PersonaReport
back. Enforces the structured-output contract and clamps scores to the schema.
"""
from __future__ import annotations

from ..contracts import Beat, BeatScore, Episode, PersonaConfig, PersonaReport
from ..providers.factory import Providers


class PersonaAgent:
    def __init__(self, config: PersonaConfig, providers: Providers) -> None:
        self.config = config
        self.p = providers

    async def evaluate(self, episode: Episode, beats: list[Beat]) -> PersonaReport:
        report = await self.p.llm.evaluate(episode, beats, self.config)
        # Defensive normalisation: guarantee exactly one in-range score per beat
        # so the Verdict Engine (which trusts the schema) can never break.
        by_beat = {s.beat_index: s.engagement for s in report.scores}
        report.scores = [
            BeatScore(beat_index=b.index, engagement=max(0, min(100, by_beat.get(b.index, 50))))
            for b in beats
        ]
        return report
