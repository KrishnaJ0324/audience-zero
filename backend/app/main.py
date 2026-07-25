"""API Gateway (§2.3 component 10, §2.5 API surface).

FastAPI. REST for commands, SSE for progress/telemetry. The internal event bus
decouples computation from the UI theatrics.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .config import get_settings
from .event_bus import bus
from .pipeline import Pipeline

settings = get_settings()
pipeline = Pipeline(settings=settings, bus=bus)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await pipeline.init()
    yield


app = FastAPI(title="Audience Zero", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #
class ScriptIn(BaseModel):
    title: str = "Untitled Episode"
    text: str


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "provider": pipeline.providers.kind, "version": app.version}


@app.get("/personas")
async def personas() -> list[dict]:
    return [
        {
            "id": p.id, "name": p.name, "archetype": p.archetype,
            "model": p.model, "color": p.color, "audience_weight": p.audience_weight,
        }
        for p in pipeline.registry.load()
    ]


@app.get("/scripts")
async def list_scripts() -> list[dict]:
    out = []
    for path in sorted(settings.scripts_dir.glob("*.txt")):
        out.append({"name": path.stem, "text": path.read_text(encoding="utf-8")})
    return out


# --- §2.5: POST /episodes -------------------------------------------------- #
# FastAPI can't mix a JSON body model with Form/File on one route, so we branch
# on content-type: multipart => audio upload; anything else => JSON script.
@app.post("/episodes")
async def create_episode(request: Request):
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        audio = form.get("audio")
        title = str(form.get("title") or "")
        if audio is None or not hasattr(audio, "read"):
            raise HTTPException(400, "multipart upload must include an 'audio' file")
        data = await audio.read()  # type: ignore[union-attr]
        ep = await pipeline.ingest_audio(title or audio.filename, data, audio.filename)  # type: ignore[union-attr]
        return ep.model_dump()
    try:
        body = await request.json()
        payload = ScriptIn(**body)
    except Exception:
        raise HTTPException(400, "Provide JSON {title,text} or a multipart audio upload")
    ep = await pipeline.ingest_script(payload.title, payload.text)
    return ep.model_dump()


# --- §2.5: POST /episodes/{id}/panel (async) ------------------------------- #
@app.post("/episodes/{episode_id}/panel")
async def trigger_panel(episode_id: str, parent: str | None = None):
    episode = await pipeline.store.get_episode(episode_id)
    if not episode:
        raise HTTPException(404, "episode not found")
    run_id = pipeline.new_run_id()

    async def _bg():
        try:
            await pipeline.run_panel(episode, run_id, parent_run_id=parent)
        except Exception:  # noqa: BLE001 — surfaced via SSE error event
            pass

    asyncio.create_task(_bg())
    return {"run_id": run_id, "episode_id": episode_id}


# --- §2.5: GET /runs/{id}/events (SSE) ------------------------------------- #
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


# --- §2.5: GET /runs/{id} -------------------------------------------------- #
@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    run = await pipeline.store.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run.model_dump()


@app.get("/runs")
async def list_runs(limit: int = 30):
    return [r.model_dump() for r in await pipeline.store.list_runs(limit)]


@app.get("/episodes/{episode_id}")
async def get_episode(episode_id: str):
    ep = await pipeline.store.get_episode(episode_id)
    if not ep:
        raise HTTPException(404, "episode not found")
    return ep.model_dump()


# --- §2.5: POST /runs/{id}/revise ------------------------------------------ #
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


# --- §2.10: POST /runs/{id}/sweep (Population Sweep, stretch) --------------- #
@app.post("/runs/{run_id}/sweep")
async def population_sweep(run_id: str, n: int = 200):
    n = max(24, min(n, 1000))
    sweep = await pipeline.population_sweep(run_id, n=n)
    return sweep.model_dump()


# --- re-run (before/after) ------------------------------------------------- #
@app.post("/runs/{run_id}/rerun")
async def rerun(run_id: str):
    parent = await pipeline.store.get_run(run_id)
    if not parent:
        raise HTTPException(404, "run not found")
    if not parent.revised_scene:
        raise HTTPException(400, "revise the run before re-running")
    child, cmp = await pipeline.rerun_with_fix(run_id)
    return {"child_run_id": child.id, "before_after": cmp.model_dump(), "run": child.model_dump()}


# --- audio static ---------------------------------------------------------- #
@app.get("/audio/{filename}")
async def get_audio(filename: str):
    path = settings.audio_dir / Path(filename).name
    if not path.exists():
        raise HTTPException(404, "audio not found")
    return FileResponse(path, media_type="audio/wav")


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
