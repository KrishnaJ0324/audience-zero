"""Coordinator that wires the services into the producer workflow.

Kept separate from the HTTP layer so it can be driven from tests, the seed
script, or the API identically. Builds the frozen AnalysisRun payload.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import hashlib
import json
import re
import secrets
import uuid

from .config import Settings, get_settings
from .contracts import (
    AnalysisRun,
    BeforeAfter,
    CalibrationSummary,
    Comment,
    EpisodeMeta,
    EvidenceSpan,
    JobState,
    Project,
    PersonaConfig,
    RevisionVariant,
    RunManifest,
    Version,
)
from .event_bus import EventBus, bus as default_bus
from .events import Event
from .providers.factory import Providers, build_providers
from .services import analysis, evidence, population_sweep, verdict_engine
from .services.audio_production import AudioProductionService
from .services.ingestion import IngestionService
from .services.orchestrator import PanelOrchestrator
from .services.persona_registry import PersonaRegistry
from .services.revision import RevisionService
from .services.session_store import SessionStore

_DEFAULT_PROJECT_ID = "proj_default"

# palette for auto-assigned custom-persona curve colours (distinct from built-ins)
_CUSTOM_PALETTE = [
    "#0e7490", "#9d174d", "#4d7c0f", "#7c2d12", "#1e3a8a",
    "#a16207", "#0f766e", "#9f1239", "#3730a3", "#57534e",
]


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _sid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


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

    # ------------------------------------------------------------------ #
    # Hierarchy: Project -> Episode -> Version
    # ------------------------------------------------------------------ #
    async def create_project(self, name: str, description: str = "") -> Project:
        p = Project(id=_sid("proj"), name=name or "Untitled Project", description=description)
        await self.store.save_project(p)
        return p

    async def _ensure_default_project(self) -> str:
        existing = await self.store.get_project(_DEFAULT_PROJECT_ID)
        if not existing:
            await self.store.save_project(
                Project(id=_DEFAULT_PROJECT_ID, name="Workspace",
                        description="Default workspace for ad-hoc analyses.")
            )
        return _DEFAULT_PROJECT_ID

    async def create_episode(self, project_id: str, title: str) -> EpisodeMeta:
        e = EpisodeMeta(id=_sid("ep"), project_id=project_id, title=title or "Untitled Episode")
        await self.store.save_episode(e)
        return e

    async def add_script_version(
        self, title: str, text: str,
        project_id: str | None = None, episode_id: str | None = None,
        label: str = "v1", parent_version_id: str | None = None,
    ) -> Version:
        version = await self.ingestion.ingest_script(title, text)
        return await self._attach_and_save(version, project_id, episode_id, label, parent_version_id)

    async def add_audio_version(
        self, title: str, data: bytes, filename: str,
        project_id: str | None = None, episode_id: str | None = None,
        label: str = "v1", parent_version_id: str | None = None,
    ) -> Version:
        version = await self.ingestion.ingest_audio(title, data, filename)
        return await self._attach_and_save(version, project_id, episode_id, label, parent_version_id)

    async def _attach_and_save(
        self, version: Version, project_id: str | None, episode_id: str | None,
        label: str, parent_version_id: str | None,
    ) -> Version:
        pid = project_id or await self._ensure_default_project()
        eid = episode_id or (await self.create_episode(pid, version.title)).id
        version.project_id = pid
        version.episode_id = eid
        version.label = label
        version.parent_version_id = parent_version_id
        await self.store.save_version(version)
        return version

    # Back-compat helpers used by tests/seed: create a fresh episode + version.
    async def ingest_script(self, title: str, text: str) -> Version:
        return await self.add_script_version(title, text)

    async def ingest_audio(self, title: str, data: bytes, filename: str) -> Version:
        return await self.add_audio_version(title, data, filename)

    # ------------------------------------------------------------------ #
    # Persona roster (built-in + user-defined)
    # ------------------------------------------------------------------ #
    async def roster(self) -> list[PersonaConfig]:
        """The panel for a run: the six built-ins plus every enabled custom
        persona. Custom personas auto-join all new analyses."""
        built = self.registry.load()
        customs = [p for p in await self.store.list_personas() if p.enabled]
        return built + customs

    async def list_custom_personas(self) -> list[PersonaConfig]:
        return await self.store.list_personas()

    async def create_persona(
        self, name: str, archetype: str, system_prompt: str,
        model: str | None = None, color: str | None = None,
    ) -> PersonaConfig:
        if not (name or "").strip():
            raise ValueError("persona needs a name")
        if not (system_prompt or "").strip():
            raise ValueError("persona needs prompt text")
        customs = await self.store.list_personas()
        used = {p.color for p in customs} | {p.color for p in self.registry.load()}
        if not color:
            color = next((c for c in _CUSTOM_PALETTE if c not in used),
                         _CUSTOM_PALETTE[len(customs) % len(_CUSTOM_PALETTE)])
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:20] or "voice"
        persona = PersonaConfig(
            id=_sid("cp"), name=name.strip(),
            archetype=(archetype or "Custom listener").strip(),
            model=model or self.s.default_persona_model,
            system_prompt=system_prompt.strip(),
            voice_id=f"{slug}_voice", color=color,
            custom=True, enabled=True, created_at=_now(),
        )
        await self.store.save_persona(persona)
        return persona

    async def delete_persona(self, persona_id: str) -> None:
        p = await self.store.get_persona(persona_id)
        if not p:
            raise ValueError("custom persona not found")
        await self.store.delete_persona(persona_id)

    async def chat_persona(self, messages: list[dict]) -> dict:
        """Multi-turn persona designer. Returns {reply, draft}. Uses the model
        when a key is present; otherwise a deterministic template assistant
        (both providers implement ``chat_persona``)."""
        fn = getattr(self.providers.llm, "chat_persona", None)
        if fn is None:
            raise ValueError("persona chat is unavailable for this provider")
        return await fn(messages)

    # ------------------------------------------------------------------ #
    # Analysis run
    # ------------------------------------------------------------------ #
    def new_run_id(self) -> str:
        return _sid("run")

    def _manifest(self, run_id: str, version: Version, personas, started: str) -> RunManifest:
        sig_src = version.transcript + "||" + "|".join(
            f"{p.id}:{p.model}:{json.dumps(p.weights, sort_keys=True)}" for p in personas
        ) + "||" + self.providers.kind
        seed = hashlib.sha256(sig_src.encode()).hexdigest()[:16]
        models = {
            "segmenter": self.s.segmenter_model,
            "revision": self.s.revision_model,
            "tts": self.s.tts_model,
            **{p.id: p.model for p in personas},
        }
        from . import __version__
        return RunManifest(
            run_id=run_id, provider=self.providers.kind, models=models,
            persona_ids=[p.id for p in personas], reveal_delay_s=self.s.reveal_delay_s,
            seed_signature=seed, engine_version=__version__, started_at=started,
        )

    async def _emit_job(self, run: AnalysisRun) -> None:
        run.job.updated_at = _now()
        run.status = {"complete": "complete", "failed": "failed", "running": "running",
                      "queued": "pending"}[run.job.status]
        await self.bus.publish(Event(type="job_state", run_id=run.id,
                                     data={"job": run.job.model_dump(), "status": run.status}))

    async def run_panel(
        self, version: Version, run_id: str, parent_run_id: str | None = None,
        speak_verdicts: int = 2,
    ) -> AnalysisRun:
        personas = await self.roster()
        started = _now()
        run = AnalysisRun(
            id=run_id, project_id=version.project_id, episode_id=version.episode_id,
            version_id=version.id, parent_run_id=parent_run_id, created_at=started,
            episode_title=version.title, version_label=version.label,
            job=JobState(status="running", stage="scoring", progress=0.1, attempts=1),
            run_manifest=self._manifest(run_id, version, personas, started),
        )
        await self.store.save_run(run)
        await self.bus.publish(Event(type="run_started", run_id=run_id, data={
            "episode_id": version.episode_id, "version_id": version.id,
            "title": version.title, "provider": self.providers.kind,
            "parent_run_id": parent_run_id,
        }))
        await self._emit_job(run)
        try:
            reports = await self.orchestrator.run_panel(run_id, version, version.beats, personas)

            run.job.stage = "verdict"; run.job.progress = 0.7
            await self._emit_job(run)
            verdict = verdict_engine.judge(reports, personas, len(version.beats))
            conf = analysis.confidence(reports, len(version.beats), len(personas))
            spans, diagnostics = evidence.spans_and_diagnostics(version, reports, verdict, personas)
            spans = await self._enrich_evidence(version, verdict, diagnostics, spans)
            actual = await self.store.get_actual(version.episode_id)
            calibration = analysis.calibrate(verdict.retention_curve, actual)

            # spoken verdicts (cast voices) — the 'producing' stage
            run.job.stage = "producing"; run.job.progress = 0.85
            await self._emit_job(run)
            pmap = {p.id: p for p in personas}
            ranked = sorted(reports, key=lambda r: (r.skip_at_beat is None, -r.confidence))
            for r in ranked[: max(0, speak_verdicts)]:
                persona = pmap.get(r.persona_id)
                if persona:
                    r.verdict_audio_path = await self.audio.speak_verdict(r, persona)

            run.reports = reports
            run.verdict = verdict
            run.confidence = conf
            run.evidence_spans = spans
            run.diagnostics = diagnostics
            run.calibration_summary = calibration
            run.run_manifest.finished_at = _now()
            run.run_manifest.duration_s = round(
                (_dt.datetime.fromisoformat(run.run_manifest.finished_at)
                 - _dt.datetime.fromisoformat(started)).total_seconds(), 2)
            run.job = JobState(status="complete", stage="done", progress=1.0, attempts=run.job.attempts)
            await self.store.save_run(run)

            await self.bus.publish(Event(type="verdict_ready", run_id=run_id,
                                         data={"verdict": verdict.model_dump(),
                                               "confidence": conf.model_dump()}))
            await self.bus.publish(Event(type="evidence_ready", run_id=run_id, data={
                "evidence_spans": [s.model_dump() for s in spans],
                "diagnostics": [d.model_dump() for d in diagnostics],
            }))
            await self._emit_job(run)
            await self.bus.publish(Event(type="run_complete", run_id=run_id,
                                         data={"run": run.model_dump()}))
            return run
        except Exception as exc:  # noqa: BLE001
            run.job = JobState(status="failed", stage=run.job.stage, error=str(exc)[:300],
                               attempts=run.job.attempts)
            await self.store.save_run(run)
            await self._emit_job(run)
            await self.bus.publish(Event(type="error", run_id=run_id, data={"error": str(exc)}))
            raise

    async def _enrich_evidence(self, version, verdict, diagnostics, spans):
        """Model-enriched evidence (behind key): ask the LLM to cite verbatim
        spans on the weakest beat. Deterministic heuristic spans always remain;
        this only adds source='model' spans, and any failure is swallowed."""
        cite = getattr(self.providers.llm, "cite_evidence", None)
        if self.providers.kind != "openai" or cite is None or not verdict:
            return spans
        wb = next((b for b in version.beats if b.index == verdict.weakest_beat), None)
        if not wb:
            return spans
        top = next((d for d in diagnostics if d.beat_index == wb.index), None)
        reason = top.summary if top else "boring or repetitive"
        kind = top.type if top else "boredom"
        try:
            quotes = await cite(wb.text, reason)
        except Exception:
            return spans
        for i, q in enumerate(quotes):
            idx = wb.text.lower().find(str(q).lower())
            if idx < 0:
                continue
            tl = len(wb.text)
            frac = idx / max(tl, 1)
            span = wb.end_s - wb.start_s
            spans.append(EvidenceSpan(
                id=f"ev_{wb.index}_model_{i}", beat_index=wb.index,
                kind=kind if kind in ("recap", "crowded", "no_hook", "trope", "boredom", "hook", "payoff") else "boredom",
                char_start=idx, char_end=min(tl, idx + len(q)),
                start_s=round(wb.start_s + frac * span, 2),
                end_s=round(wb.start_s + (min(tl, idx + len(q)) / max(tl, 1)) * span, 2),
                quote=wb.text[idx:idx + len(q)][:160], persona_ids=[], source="model",
            ))
        return spans

    async def retry_run(self, run_id: str) -> str:
        """Re-enqueue a failed run's analysis on the same version."""
        run = await self.store.get_run(run_id)
        if not run:
            raise ValueError("run not found")
        version = await self.store.get_version(run.version_id)
        if not version:
            raise ValueError("version not found")
        await self.run_panel(version, run_id, parent_run_id=run.parent_run_id)
        return run_id

    # ------------------------------------------------------------------ #
    # Revision variants
    # ------------------------------------------------------------------ #
    async def revise_run(self, run_id: str, target: str = "weakest") -> AnalysisRun:
        run = await self.store.get_run(run_id)
        if not run or not run.verdict:
            raise ValueError("run not found or has no verdict")
        version = await self.store.get_version(run.version_id)
        if not version:
            raise ValueError("version not found")
        target_beat = (len(version.beats) - 1) if target == "ending" else run.verdict.weakest_beat
        beat = next((b for b in version.beats if b.index == target_beat), version.beats[0])

        await self.bus.publish(Event(type="revision_started", run_id=run_id,
                                     data={"beat_index": target_beat, "target": target}))
        scene = await self.revision.revise(beat, run.reports, target_beat, mode=target)
        personas = await self.roster()
        voice_map = {p.name.upper(): p.voice_id for p in personas}
        produced = await self.audio.produce_scene(scene, voice_map)

        variant = RevisionVariant(
            id=_sid("var"), target=target, beat_index=target_beat,  # type: ignore[arg-type]
            new_text=scene.new_text, change_rationale=scene.change_rationale,
            casting=scene.casting, produced_audio=produced, status="proposed",
        )
        run.revision_variants.append(variant)
        # legacy mirrors (kept until the FE migrates to revision_variants)
        run.revised_scene = scene
        run.produced_audio = produced
        run.revision_target = target  # type: ignore[assignment]
        await self.store.save_run(run)

        await self.bus.publish(Event(type="variant_added", run_id=run_id,
                                     data={"variant": variant.model_dump()}))
        await self.bus.publish(Event(type="revision_ready", run_id=run_id,
                                     data={"scene": scene.model_dump()}))
        await self.bus.publish(Event(type="audio_ready", run_id=run_id,
                                     data={"produced_audio": produced.model_dump()}))
        return run

    async def set_variant_consent(self, run_id: str, variant_id: str, consent: str) -> AnalysisRun:
        run = await self.store.get_run(run_id)
        if not run:
            raise ValueError("run not found")
        v = next((x for x in run.revision_variants if x.id == variant_id), None)
        if not v:
            raise ValueError("variant not found")
        v.disclosure.voice_consent = consent  # type: ignore[assignment]
        await self.store.save_run(run)
        await self.bus.publish(Event(type="variant_updated", run_id=run_id,
                                     data={"variant_id": variant_id, "consent": consent}))
        return run

    async def set_variant_status(self, run_id: str, variant_id: str, status: str, notes: str = "") -> AnalysisRun:
        run = await self.store.get_run(run_id)
        if not run:
            raise ValueError("run not found")
        for v in run.revision_variants:
            if v.id == variant_id:
                v.status = status  # type: ignore[assignment]
                if notes:
                    v.notes = notes
            elif status == "accepted":
                # only one accepted variant at a time
                if v.status == "accepted":
                    v.status = "proposed"
        await self.store.save_run(run)
        await self.bus.publish(Event(type="variant_updated", run_id=run_id,
                                     data={"variant_id": variant_id, "status": status}))
        return run

    # ------------------------------------------------------------------ #
    # Re-run with a fix (before/after)
    # ------------------------------------------------------------------ #
    async def rerun_with_fix(self, parent_run_id: str, variant_id: str | None = None) -> tuple[AnalysisRun, BeforeAfter]:
        parent = await self.store.get_run(parent_run_id)
        if not parent or not parent.verdict or not parent.revision_variants:
            raise ValueError("parent run must be revised before re-run")
        variant = next((v for v in parent.revision_variants if v.id == variant_id), None) \
            or next((v for v in parent.revision_variants if v.status == "accepted"), None) \
            or parent.revision_variants[-1]

        version = await self.store.get_version(parent.version_id)
        if not version:
            raise ValueError("version not found")

        # new Version = parent version with the revised beat swapped in
        patched = version.model_copy(deep=True)
        wi = variant.beat_index
        for b in patched.beats:
            if b.index == wi:
                b.text = variant.new_text
                b.summary = "(revised) " + b.summary
        patched.id = _sid("ver")
        patched.parent_version_id = version.id
        patched.label = f"{version.label}+fix-b{wi + 1}"
        patched.title = version.title
        await self.store.save_version(patched)

        child_id = self.new_run_id()
        child = await self.run_panel(patched, child_id, parent_run_id=parent_run_id)
        cmp = verdict_engine.before_after(
            parent.verdict, child.verdict, parent_run_id, child_id, wi,
            target=variant.target if variant.target in ("weakest", "ending") else "weakest",
        )
        # link the variant to its re-run
        variant.rerun_id = child_id
        variant.before_after = cmp
        await self.store.save_run(parent)
        await self.bus.publish(Event(type="run_complete", run_id=child_id,
                                     data={"before_after": cmp.model_dump()}))
        return child, cmp

    # ------------------------------------------------------------------ #
    # Calibration + sweep
    # ------------------------------------------------------------------ #
    async def attach_actual(self, episode_id: str, retention: list[float]) -> None:
        await self.store.save_actual(episode_id, retention)

    async def recalibrate_run(self, run_id: str) -> CalibrationSummary:
        run = await self.store.get_run(run_id)
        if not run or not run.verdict:
            raise ValueError("run not found")
        actual = await self.store.get_actual(run.episode_id)
        cal = analysis.calibrate(run.verdict.retention_curve, actual)
        run.calibration_summary = cal
        await self.store.save_run(run)
        return cal

    async def attach_actual_for_run(self, run_id: str, retention: list[float]) -> CalibrationSummary:
        run = await self.store.get_run(run_id)
        if not run:
            raise ValueError("run not found")
        await self.store.save_actual(run.episode_id, [max(0.0, min(1.0, float(x))) for x in retention])
        return await self.recalibrate_run(run_id)

    async def simulate_actual_for_run(self, run_id: str) -> CalibrationSummary:
        run = await self.store.get_run(run_id)
        if not run or not run.verdict:
            raise ValueError("run not found or has no verdict")
        actual = analysis.simulate_actual(run.verdict.retention_curve, run.episode_id)
        await self.store.save_actual(run.episode_id, actual)
        return await self.recalibrate_run(run_id)

    # ------------------------------------------------------------------ #
    # Diagnostics collaboration
    # ------------------------------------------------------------------ #
    async def _mutate_diagnostic(self, run_id: str, diag_id: str, fn) -> AnalysisRun:
        run = await self.store.get_run(run_id)
        if not run:
            raise ValueError("run not found")
        diag = next((d for d in run.diagnostics if d.id == diag_id), None)
        if not diag:
            raise ValueError("diagnostic not found")
        fn(diag)
        await self.store.save_run(run)
        await self.bus.publish(Event(type="variant_updated", run_id=run_id,
                                     data={"diagnostic_id": diag_id}))
        return run

    async def add_comment(self, run_id: str, diag_id: str, author: str, body: str) -> AnalysisRun:
        return await self._mutate_diagnostic(
            run_id, diag_id,
            lambda d: d.comments.append(Comment(id=_sid("cm"), author=author or "producer", body=body)))

    async def assign_diagnostic(self, run_id: str, diag_id: str, assignee: str | None) -> AnalysisRun:
        return await self._mutate_diagnostic(run_id, diag_id, lambda d: setattr(d, "assignee", assignee or None))

    async def set_diagnostic_status(self, run_id: str, diag_id: str, status: str) -> AnalysisRun:
        return await self._mutate_diagnostic(run_id, diag_id, lambda d: setattr(d, "status", status))

    # ------------------------------------------------------------------ #
    # Sharing (read-only tokens)
    # ------------------------------------------------------------------ #
    async def create_share(self, run_id: str) -> str:
        run = await self.store.get_run(run_id)
        if not run:
            raise ValueError("run not found")
        token = secrets.token_urlsafe(12)
        await self.store.save_share(token, run_id, _now())
        return token

    async def get_shared_run(self, token: str) -> AnalysisRun | None:
        run_id = await self.store.get_share(token)
        if not run_id:
            return None
        return await self.store.get_run(run_id)

    async def population_sweep(self, run_id: str, n: int = 200):
        run = await self.store.get_run(run_id)
        if not run:
            raise ValueError("run not found")
        version = await self.store.get_version(run.version_id)
        if not version:
            raise ValueError("version not found")
        personas = await self.roster()
        return population_sweep.sweep(version, personas, n=n)
