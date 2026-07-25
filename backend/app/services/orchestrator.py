"""Panel Orchestrator (§2.3 component 4).

Fan-out: ``asyncio.gather`` one task per persona. Fan-in: collect
PersonaReports. Emits progress events onto the bus (the theatre layer consumes
these). Retries + per-agent timeout; a failed agent degrades the panel to N−1,
it never blocks the whole run.

Computation is real; streaming is theatre (#4): agents run as genuine parallel
one-shot calls, then we drip ``beat_scored`` events out with a small delay so
the dashboard can animate the curves drawing in. We never claim the animation
is live inference.
"""
from __future__ import annotations

import asyncio

from ..config import Settings
from ..contracts import Beat, Episode, PersonaConfig, PersonaReport
from ..event_bus import EventBus
from ..events import Event
from ..providers.factory import Providers
from .persona_runtime import PersonaAgent


class PanelOrchestrator:
    def __init__(self, providers: Providers, bus: EventBus, settings: Settings) -> None:
        self.p = providers
        self.bus = bus
        self.s = settings

    async def run_panel(
        self,
        run_id: str,
        episode: Episode,
        beats: list[Beat],
        personas: list[PersonaConfig],
    ) -> list[PersonaReport]:
        await self.bus.publish(Event(type="beats_ready", run_id=run_id, data={
            "beats": [b.model_dump() for b in beats],
            "personas": [
                {"id": p.id, "name": p.name, "archetype": p.archetype, "color": p.color}
                for p in personas
            ],
        }))

        async def one(persona: PersonaConfig) -> PersonaReport | None:
            agent = PersonaAgent(persona, self.p)
            await self.bus.publish(Event(type="agent_started", run_id=run_id,
                                         data={"persona_id": persona.id, "name": persona.name}))
            for attempt in range(self.s.per_agent_retries + 1):
                try:
                    report = await asyncio.wait_for(
                        agent.evaluate(episode, beats), timeout=self.s.per_agent_timeout_s
                    )
                    await self._reveal(run_id, persona, report)
                    await self.bus.publish(Event(type="agent_done", run_id=run_id, data={
                        "persona_id": persona.id,
                        "report": report.model_dump(),
                    }))
                    return report
                except Exception as exc:  # noqa: BLE001 — degrade, don't crash
                    if attempt >= self.s.per_agent_retries:
                        await self.bus.publish(Event(type="agent_failed", run_id=run_id, data={
                            "persona_id": persona.id, "error": str(exc)[:200],
                        }))
                        return None
                    await asyncio.sleep(0.4)
            return None

        results = await asyncio.gather(*(one(p) for p in personas))
        reports = [r for r in results if r is not None]
        return reports

    async def _reveal(self, run_id: str, persona: PersonaConfig, report: PersonaReport) -> None:
        """Progressive per-beat reveal — theatre pacing for the curve animation."""
        for s in report.scores:
            await self.bus.publish(Event(type="beat_scored", run_id=run_id, data={
                "persona_id": persona.id,
                "beat_index": s.beat_index,
                "engagement": s.engagement,
                "color": persona.color,
            }))
            if self.s.reveal_delay_s > 0:
                await asyncio.sleep(self.s.reveal_delay_s)
