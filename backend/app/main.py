"""API Gateway — v2 producer workflow.

FastAPI. REST for commands, SSE for progress/telemetry. Hierarchy:
Project -> Episode -> Version -> AnalysisRun -> RevisionVariant. The event bus
decouples computation from UI theatrics and replays history to late/reconnecting
subscribers.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .config import get_settings
from .event_bus import bus
from .pipeline import Pipeline
from .providers import wavtools
from .services import report_pdf, summary as summary_svc

settings = get_settings()
pipeline = Pipeline(settings=settings, bus=bus)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await pipeline.init()
    yield


app = FastAPI(title="Audience Zero", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScriptIn(BaseModel):
    title: str = "Untitled Episode"
    text: str
    label: str = "v1"


class ProjectIn(BaseModel):
    name: str
    description: str = ""


# --------------------------------------------------------------------------- #
# Meta
# --------------------------------------------------------------------------- #
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "provider": pipeline.providers.kind, "version": app.version}


# --------------------------------------------------------------------------- #
# Deployment verification gates (Databricks Apps). Existence checks only —
# a secret's value is never returned or logged.
# --------------------------------------------------------------------------- #
@app.get("/debug/env-check")
async def env_check() -> dict:
    return {
        "openai_key_present": bool(settings.effective_openai_key),
        "openai_api_key_env": "OPENAI_API_KEY" in os.environ,
        "az_openai_api_key_env": "AZ_OPENAI_API_KEY" in os.environ,
        "resolved_provider": settings.resolved_provider,
        "db_path": str(settings.db_path),
        "audio_dir": str(settings.audio_dir),
        "db_writable": os.access(settings.db_path.parent, os.W_OK),
        "audio_writable": os.access(settings.audio_dir, os.W_OK),
        "personas": len(pipeline.registry.load()),
    }


@app.get("/debug/ffmpeg")
async def ffmpeg_check() -> dict:
    # Informational only: the mixer is the stdlib `wave` implementation, so a
    # missing ffmpeg never degrades audio production.
    return {"ffmpeg_available": shutil.which("ffmpeg") is not None, "mixer": "stdlib-wave"}


@app.get("/debug/sse-counter")
async def sse_counter():
    """Proxy-buffering probe: the ten numbers must arrive ~1/second, not in one
    burst at the end. A burst means switch the dashboard to 1s polling."""

    async def gen():
        for i in range(10):
            yield {"event": "tick", "data": str(i)}
            await asyncio.sleep(1.0)

    return EventSourceResponse(gen())


@app.get("/personas")
async def personas() -> list[dict]:
    """The persona library — every definition (built-in + custom). Enablement is
    chosen per project (see /projects/{id}/personas)."""
    return [_persona_dto(p) for p in await pipeline.all_personas()]


class ToggleIn(BaseModel):
    enabled: bool


@app.get("/projects/{project_id}/personas")
async def project_personas(project_id: str) -> list[dict]:
    """Every persona with its ENABLED state for this project. Only enabled
    personas run when analyzing episodes in the project."""
    if not await pipeline.store.get_project(project_id):
        raise HTTPException(404, "project not found")
    return [_persona_dto(p) for p in await pipeline.all_personas(project_id)]


@app.post("/projects/{project_id}/personas/{persona_id}/toggle")
async def toggle_project_persona(project_id: str, persona_id: str, payload: ToggleIn):
    if not await pipeline.store.get_project(project_id):
        raise HTTPException(404, "project not found")
    all_p = await pipeline.set_persona_enabled(project_id, persona_id, payload.enabled)
    return [_persona_dto(p) for p in all_p]


class PersonaIn(BaseModel):
    name: str
    archetype: str = "Custom listener"
    system_prompt: str
    model: str | None = None
    color: str | None = None


@app.post("/personas")
async def create_persona(payload: PersonaIn):
    p = await pipeline.create_persona(
        payload.name, payload.archetype, payload.system_prompt,
        model=payload.model, color=payload.color,
    )
    return _persona_dto(p)


@app.delete("/personas/{persona_id}")
async def delete_persona(persona_id: str):
    await pipeline.delete_persona(persona_id)
    return {"deleted": persona_id}


class PersonaChatIn(BaseModel):
    messages: list[dict]


@app.post("/personas/chat")
async def persona_chat(payload: PersonaChatIn):
    return await pipeline.chat_persona(payload.messages)


@app.get("/scripts")
async def list_scripts() -> list[dict]:
    return [
        {"name": path.stem, "text": path.read_text(encoding="utf-8")}
        for path in sorted(settings.scripts_dir.glob("*.txt"))
    ]


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #
@app.post("/projects")
async def create_project(payload: ProjectIn):
    p = await pipeline.create_project(payload.name, payload.description)
    return p.model_dump()


@app.get("/projects")
async def list_projects():
    return [p.model_dump() for p in await pipeline.store.list_projects()]


@app.get("/projects/{project_id}")
async def get_project(project_id: str):
    p = await pipeline.store.get_project(project_id)
    if not p:
        raise HTTPException(404, "project not found")
    episodes = await pipeline.store.list_episodes(project_id)
    return {"project": p.model_dump(), "episodes": [e.model_dump() for e in episodes]}


# --------------------------------------------------------------------------- #
# Episodes + Versions
# --------------------------------------------------------------------------- #
async def _ingest(request: Request, project_id: str | None, episode_id: str | None,
                  label: str = "v1", parent_version_id: str | None = None):
    """Shared script(JSON)/audio(multipart) ingestion → a saved Version."""
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        audio = form.get("audio")
        title = str(form.get("title") or "")
        lbl = str(form.get("label") or label)
        if audio is None or not hasattr(audio, "read"):
            raise HTTPException(400, "multipart upload must include an 'audio' file")
        data = await audio.read()  # type: ignore[union-attr]
        return await pipeline.add_audio_version(
            title or audio.filename, data, audio.filename,  # type: ignore[union-attr]
            project_id=project_id, episode_id=episode_id, label=lbl,
            parent_version_id=parent_version_id)
    try:
        body = await request.json()
        payload = ScriptIn(**body)
    except Exception:
        raise HTTPException(400, "Provide JSON {title,text} or a multipart audio upload")
    return await pipeline.add_script_version(
        payload.title, payload.text, project_id=project_id, episode_id=episode_id,
        label=payload.label or label, parent_version_id=parent_version_id)


@app.post("/projects/{project_id}/episodes")
async def create_episode_in_project(project_id: str, request: Request):
    project = await pipeline.store.get_project(project_id)
    if not project:
        raise HTTPException(404, "project not found")
    episode = await pipeline.create_episode(project_id, "Untitled Episode")
    version = await _ingest(request, project_id, episode.id, label="v1")
    # name the episode after the version title
    episode.title = version.title
    await pipeline.store.save_episode(episode)
    return {"episode": episode.model_dump(), "version": version.model_dump()}


@app.get("/episodes/{episode_id}")
async def get_episode(episode_id: str):
    episode = await pipeline.store.get_episode(episode_id)
    if not episode:
        raise HTTPException(404, "episode not found")
    versions = await pipeline.store.list_versions(episode_id)
    runs = await pipeline.store.list_runs_for_episode(episode_id)
    return {
        "episode": episode.model_dump(),
        "versions": [v.model_dump() for v in versions],
        "runs": [r.model_dump() for r in runs],
    }


@app.post("/episodes/{episode_id}/versions")
async def add_version(episode_id: str, request: Request, label: str = "v", parent: str | None = None):
    episode = await pipeline.store.get_episode(episode_id)
    if not episode:
        raise HTTPException(404, "episode not found")
    version = await _ingest(request, episode.project_id, episode_id, label=label,
                            parent_version_id=parent)
    return version.model_dump()


@app.get("/versions/{version_id}")
async def get_version(version_id: str):
    v = await pipeline.store.get_version(version_id)
    if not v:
        raise HTTPException(404, "version not found")
    return v.model_dump()


# Convenience: create an ad-hoc episode+version in the default workspace (the
# quick "paste script and run" flow). Mirrors the old POST /episodes.
@app.post("/episodes")
async def quick_ingest(request: Request):
    version = await _ingest(request, None, None)
    return version.model_dump()


# --------------------------------------------------------------------------- #
# Analysis runs
# --------------------------------------------------------------------------- #
def _analyze_bg(version, run_id: str, parent: str | None):
    async def _bg():
        try:
            await pipeline.run_panel(version, run_id, parent_run_id=parent)
        except Exception:  # noqa: BLE001 — surfaced via SSE error/job_state
            pass
    asyncio.create_task(_bg())


@app.post("/versions/{version_id}/analyze")
async def analyze_version(version_id: str, parent: str | None = None):
    version = await pipeline.store.get_version(version_id)
    if not version:
        raise HTTPException(404, "version not found")
    run_id = pipeline.new_run_id()
    _analyze_bg(version, run_id, parent)
    return {"run_id": run_id, "version_id": version_id}


# Back-compat: analyze by (ad-hoc) version id via the old panel path.
@app.post("/episodes/{version_id}/panel")
async def trigger_panel(version_id: str, parent: str | None = None):
    return await analyze_version(version_id, parent)


@app.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request):
    async def gen():
        q = await bus.subscribe(run_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield event.sse()
        finally:
            await bus.unsubscribe(run_id, q)

    return EventSourceResponse(gen())


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    run = await pipeline.store.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run.model_dump()


@app.get("/runs")
async def list_runs(limit: int = 30):
    return [r.model_dump() for r in await pipeline.store.list_runs(limit)]


@app.post("/runs/{run_id}/retry")
async def retry_run(run_id: str):
    run = await pipeline.store.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    version = await pipeline.store.get_version(run.version_id)
    if not version:
        raise HTTPException(400, "run has no analyzable version")
    _analyze_bg(version, run_id, run.parent_run_id)
    return {"run_id": run_id, "status": "queued"}


# --------------------------------------------------------------------------- #
# Revisions
# --------------------------------------------------------------------------- #
@app.post("/runs/{run_id}/revise")
async def revise(run_id: str, target: str = "weakest"):
    run = await pipeline.store.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if target not in ("weakest", "ending"):
        raise HTTPException(400, "target must be 'weakest' or 'ending'")

    async def _bg():
        try:
            await pipeline.revise_run(run_id, target=target)
        except Exception:  # noqa: BLE001
            pass
    asyncio.create_task(_bg())
    return {"run_id": run_id, "status": "revising", "target": target}


class VariantStatusIn(BaseModel):
    status: str
    notes: str = ""


@app.post("/runs/{run_id}/variants/{variant_id}/status")
async def variant_status(run_id: str, variant_id: str, payload: VariantStatusIn):
    if payload.status not in ("proposed", "accepted", "rejected"):
        raise HTTPException(400, "invalid status")
    run = await pipeline.set_variant_status(run_id, variant_id, payload.status, payload.notes)
    return run.model_dump()


class ConsentIn(BaseModel):
    consent: str


@app.post("/runs/{run_id}/variants/{variant_id}/consent")
async def variant_consent(run_id: str, variant_id: str, payload: ConsentIn):
    valid = ("synthetic_no_consent_needed", "consented", "pending", "unknown")
    if payload.consent not in valid:
        raise HTTPException(400, f"consent must be one of {valid}")
    run = await pipeline.set_variant_consent(run_id, variant_id, payload.consent)
    return run.model_dump()


@app.post("/runs/{run_id}/rerun")
async def rerun(run_id: str, variant: str | None = None):
    parent = await pipeline.store.get_run(run_id)
    if not parent:
        raise HTTPException(404, "run not found")
    if not parent.revision_variants:
        raise HTTPException(400, "revise the run before re-running")
    child, cmp = await pipeline.rerun_with_fix(run_id, variant_id=variant)
    return {"child_run_id": child.id, "before_after": cmp.model_dump(), "run": child.model_dump()}


@app.post("/runs/{run_id}/sweep")
async def population_sweep(run_id: str, n: int = 200):
    n = max(24, min(n, 1000))
    sweep = await pipeline.population_sweep(run_id, n=n)
    return sweep.model_dump()


# --------------------------------------------------------------------------- #
# Diagnostics collaboration
# --------------------------------------------------------------------------- #
class CommentIn(BaseModel):
    author: str = "producer"
    body: str


class AssignIn(BaseModel):
    assignee: str | None = None


class DiagStatusIn(BaseModel):
    status: str


@app.post("/runs/{run_id}/diagnostics/{diag_id}/comment")
async def add_comment(run_id: str, diag_id: str, payload: CommentIn):
    run = await pipeline.add_comment(run_id, diag_id, payload.author, payload.body)
    return run.model_dump()


@app.post("/runs/{run_id}/diagnostics/{diag_id}/assign")
async def assign_diag(run_id: str, diag_id: str, payload: AssignIn):
    run = await pipeline.assign_diagnostic(run_id, diag_id, payload.assignee)
    return run.model_dump()


@app.post("/runs/{run_id}/diagnostics/{diag_id}/status")
async def diag_status(run_id: str, diag_id: str, payload: DiagStatusIn):
    if payload.status not in ("open", "resolved", "dismissed"):
        raise HTTPException(400, "invalid status")
    run = await pipeline.set_diagnostic_status(run_id, diag_id, payload.status)
    return run.model_dump()


# --------------------------------------------------------------------------- #
# Share / export / summary
# --------------------------------------------------------------------------- #
@app.post("/runs/{run_id}/share")
async def create_share(run_id: str):
    token = await pipeline.create_share(run_id)
    return {"token": token, "path": f"/shared/{token}"}


@app.get("/shared/{token}")
async def get_shared(token: str):
    run = await pipeline.get_shared_run(token)
    if not run:
        raise HTTPException(404, "shared report not found")
    return {"read_only": True, "run": run.model_dump(),
            "summary": summary_svc.producer_summary(run)}


@app.get("/runs/{run_id}/summary")
async def run_summary(run_id: str, enrich: bool = False):
    run = await pipeline.store.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    text = summary_svc.producer_summary(run)
    enriched = False
    polish = getattr(pipeline.providers.llm, "summarize", None)
    if enrich and pipeline.providers.kind == "openai" and polish is not None:
        try:
            text = await polish(text)
            enriched = True
        except Exception:
            pass
    return {"summary": text, "enriched": enriched}


# --------------------------------------------------------------------------- #
# Calibration (prediction vs. actual)
# --------------------------------------------------------------------------- #
def _parse_retention(text: str) -> list[float]:
    """Accept JSON list, or CSV/whitespace numbers. Values >1 are treated as
    percentages and divided by 100."""
    text = text.strip()
    nums: list[float] = []
    try:
        import json as _json
        data = _json.loads(text)
        if isinstance(data, dict):
            data = data.get("retention", [])
        nums = [float(x) for x in data]
    except Exception:
        for tok in text.replace(",", " ").replace("\n", " ").split():
            try:
                nums.append(float(tok))
            except ValueError:
                pass
    return [(x / 100.0 if x > 1.0 else x) for x in nums]


class ActualIn(BaseModel):
    retention: list[float]


@app.post("/runs/{run_id}/calibrate")
async def calibrate_run(run_id: str, request: Request):
    """Attach real retention (JSON body {retention:[…]} or a CSV/text upload) and
    recompute calibration for this run."""
    import json as _json

    ctype = request.headers.get("content-type", "")
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        f = form.get("file")
        if f is not None and hasattr(f, "read"):
            raw = (await f.read()).decode("utf-8", "ignore")  # type: ignore[union-attr]
        else:
            raw = str(form.get("retention") or "")
        retention = _parse_retention(raw)
    else:
        raw = (await request.body()).decode("utf-8", "ignore")
        try:
            data = _json.loads(raw)
            retention = _parse_retention(raw if isinstance(data, (list, dict)) else raw)
        except Exception:
            retention = _parse_retention(raw)
    if not retention:
        raise HTTPException(400, "no retention values found")
    cal = await pipeline.attach_actual_for_run(run_id, retention)
    return cal.model_dump()


@app.post("/runs/{run_id}/calibrate/simulate")
async def simulate_calibration(run_id: str):
    cal = await pipeline.simulate_actual_for_run(run_id)
    return cal.model_dump()


@app.post("/runs/{run_id}/recalibrate")
async def recalibrate(run_id: str):
    cal = await pipeline.recalibrate_run(run_id)
    return cal.model_dump()


@app.get("/runs/{run_id}/report.pdf")
async def run_report_pdf(run_id: str):
    run = await pipeline.store.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    pdf = report_pdf.build_pdf(run, summary_svc.producer_summary(run))
    fname = f"audience-zero-{run_id}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})


# --------------------------------------------------------------------------- #
# Audio + waveform
# --------------------------------------------------------------------------- #
@app.get("/audio/{filename}")
async def get_audio(filename: str):
    path = settings.audio_dir / Path(filename).name
    if not path.exists():
        raise HTTPException(404, "audio not found")
    return FileResponse(path, media_type="audio/wav")


@app.get("/audio/{filename}/peaks")
async def audio_peaks(filename: str, buckets: int = 400):
    path = settings.audio_dir / Path(filename).name
    if not path.exists():
        raise HTTPException(404, "audio not found")
    return {"peaks": wavtools.peaks(str(path), max(16, min(buckets, 2000)))}


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
