"""Single-process ASGI entry point for Databricks Apps.

One process serves both halves of the product:

* the FastAPI gateway (``app.main``) mounted at ``/api`` — exactly the base the
  dashboard already calls (``frontend/src/api.ts`` defaults to ``/api``), so the
  Vite dev proxy and the deployed app expose an identical surface;
* the built React bundle from ``backend/static/`` at ``/``.

Two ordering rules, both load-bearing:

1. The ``StaticFiles`` mount on ``"/"`` is registered LAST. A mount on the root
   swallows every route added after it.
2. Starlette does **not** propagate lifespan events into a mounted sub-app, so
   the parent owns the lifespan and initialises the pipeline itself. Without
   this the SQLite schema is never created and every run 500s.

Local dev is unchanged (``uvicorn app.main:app`` behind the Vite proxy); this
module is what ``app.yaml`` runs.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import BACKEND_ROOT
from .main import app as api_app
from .main import pipeline

STATIC_DIR = BACKEND_ROOT / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await pipeline.init()
    yield


server = FastAPI(
    title="Audience Zero (single process)",
    version=api_app.version,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# 1. API first.
server.mount("/api", api_app)


# 2. Static bundle last. Missing bundle is a deploy mistake, not a crash: the
#    API stays usable and the root explains how to build it.
if (STATIC_DIR / "index.html").exists():
    server.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
else:

    @server.get("/")
    async def _missing_bundle() -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "static bundle missing",
                "fix": "cd frontend && npm run build, then copy dist/ to backend/static/",
                "expected": str(STATIC_DIR),
                "api": "/api/health",
            },
        )
