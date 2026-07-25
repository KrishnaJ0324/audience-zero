"""Coordinator that wires the services into the golden path.

Kept separate from the HTTP layer so it can be driven from tests, the seed
script, or the API identically.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import uuid

from .config import Settings, get_settings
from .contracts import BeforeAfter, Episode, PanelRun
from .event_bus import EventBus, bus as default_bus
from .events import Event
from .providers.factory import Providers, build_providers
from .services.audio_production import AudioProductionService
from .services.ingestion import IngestionService
from .services.orchestrator import PanelOrchestrator
from .services.persona_registry import PersonaRegistry
from .services.revision import RevisionService
from .services.session_store import SessionStore
from .services import population_sweep, verdict_engine


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class Pipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        bus: EventBus | None = None,
        providers: Providers | None = None,
    ) -> None:
        self.s = settings or get_settings()
        self.bus = bus or default_bus
        self.providers = providers or build_providers(self.s)
        self.registry = PersonaRegistry(self.s.personas_dir)
        self.store = SessionStore(self.s.db_path)
        self.ingestion = IngestionService(self.providers, self.s.min_beats, self.s.max_beats)
        self.orchestrator = PanelOrchestrator(self.providers, self.bus, self.s)
        self.revision = RevisionService(self.providers)
        self.audio = AudioProductionService(self.providers, self.s.audio_dir)

    async def init(self) -> None:
        await self.store.init()
        self.registry.load()

    # --- ingest ---------------------------------------------------------
    async def ingest_script(self, title: str, text: str) -> Episode:
        ep = await self.ingestion.ingest_script(title, text)
        await self.store.save_episode(ep)
        return ep

    async def ingest_audio(self, title: str, data: bytes, filename: str) -> Episode:
        ep = await self.ingestion.ingest_audio(title, data, filename)
        await self.store.save_episode(ep)
        return ep

    # --- panel ----------------------------------------------------------
    def new_run_id(self) -> str:
        return f"run_{uuid.uuid4().hex[:10]}"

    async def run_panel(
        self, episode: Episode, run_id: str, parent_run_id: str | None = None,
        speak_verdicts: int = 2,
    ) -> PanelRun:
        personas = self.registry.load()
        run = PanelRun(
            id=run_id, episode_id=episode.id, status="running",
            parent_run_id=parent_run_id, created_at=_now(), episode_title=episode.title,
        )
        await self.store.save_run(run)
        await self.bus.publish(Event(type="run_started", run_id=run_id, data={
            "episode_id": episode.id, "title": episode.title,
            "provider": self.providers.kind, "parent_run_id": parent_run_id,
        }))
        try:
            reports = await self.orchestrator.run_panel(run_id, episode, episode.beats, personas)
            verdict = verdict_engine.judge(reports, personas, len(episode.beats))

            # render the loudest N verdicts to speech (cast voices)
            pmap = {p.id: p for p in personas}
            ranked = sorted(reports, key=lambda r: (r.skip_at_beat is None, -r.confidence))
            for r in ranked[: max(0, speak_verdicts)]:
                persona = pmap.get(r.persona_id)
                if persona:
                    r.verdict_audio_path = await self.audio.speak_verdict(r, persona)

            run.reports = reports
            run.verdict = verdict
            run.status = "complete"
            await self.store.save_run(run)
            await self.bus.publish(Event(type="verdict_ready", run_id=run_id,
                                         data={"verdict": verdict.model_dump()}))
            await self.bus.publish(Event(type="run_complete", run_id=run_id,
                                         data={"run": run.model_dump()}))
            return run
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            await self.store.save_run(run)
            await self.bus.publish(Event(type="error", run_id=run_id, data={"error": str(exc)}))
            raise

    # --- revise (fix weakest beat, or strengthen the ending) -----------
    async def revise_run(self, run_id: str, target: str = "weakest") -> PanelRun:
        run = await self.store.get_run(run_id)
        if not run or not run.verdict:
            raise ValueError("run not found or has no verdict")
        episode = await self.store.get_episode(run.episode_id)
        if not episode:
            raise ValueError("episode not found")
        if target == "ending":
            target_beat = len(episode.beats) - 1
        else:
            target_beat = run.verdict.weakest_beat
        beat = next((b for b in episode.beats if b.index == target_beat), episode.beats[0])

        await self.bus.publish(Event(type="revision_started", run_id=run_id,
                                     data={"beat_index": target_beat, "target": target}))
        scene = await self.revision.revise(beat, run.reports, target_beat, mode=target)
        personas = self.registry.load()
        voice_map = {p.name.upper(): p.voice_id for p in personas}
        produced = await self.audio.produce_scene(scene, voice_map)

        run.revised_scene = scene
        run.produced_audio = produced
        run.revision_target = target  # type: ignore[assignment]
        await self.store.save_run(run)
        await self.bus.publish(Event(type="revision_ready", run_id=run_id,
                                     data={"scene": scene.model_dump()}))
        await self.bus.publish(Event(type="audio_ready", run_id=run_id,
                                     data={"produced_audio": produced.model_dump()}))
        return run

    # --- population sweep (stretch) ------------------------------------
    async def population_sweep(self, run_id: str, n: int = 200):
        run = await self.store.get_run(run_id)
        if not run:
            raise ValueError("run not found")
        episode = await self.store.get_episode(run.episode_id)
        if not episode:
            raise ValueError("episode not found")
        personas = self.registry.load()
        return population_sweep.sweep(episode, personas, n=n)

    # --- re-run for before/after ---------------------------------------
    async def rerun_with_fix(self, parent_run_id: str) -> tuple[PanelRun, BeforeAfter]:
        parent = await self.store.get_run(parent_run_id)
        if not parent or not parent.verdict or not parent.revised_scene:
            raise ValueError("parent run must be revised before re-run")
        episode = await self.store.get_episode(parent.episode_id)
        if not episode:
            raise ValueError("episode not found")

        # build a patched episode: swap the REVISED beat's text for the rewrite
        # (weakest beat for a normal fix, final beat for an ending fix).
        patched = episode.model_copy(deep=True)
        wi = parent.revised_scene.beat_index
        for b in patched.beats:
            if b.index == wi:
                b.text = parent.revised_scene.new_text
                b.summary = "(revised) " + b.summary
        patched.id = f"{episode.id}_rev{uuid.uuid4().hex[:4]}"
        patched.title = episode.title + " (revised)"
        await self.store.save_episode(patched)

        child_id = self.new_run_id()
        child = await self.run_panel(patched, child_id, parent_run_id=parent_run_id)
        cmp = verdict_engine.before_after(
            parent.verdict, child.verdict, parent_run_id, child_id, wi,
            target=parent.revision_target,
        )
        await self.bus.publish(Event(type="run_complete", run_id=child_id,
                                     data={"before_after": cmp.model_dump()}))
        return child, cmp
