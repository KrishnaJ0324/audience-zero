# Repository Guidelines

## Project Structure & Module Organization

`backend/` contains the FastAPI service. Keep request/data contracts in
`backend/app/contracts.py`, endpoint wiring in `app/main.py`, orchestration and
business logic in `app/services/`, and external integrations behind
`app/providers/`. Persona behaviour is configuration: add personas as numbered
YAML files in `backend/personas/`. Demo and calibration scripts live in
`backend/data/scripts/`; generated databases and audio are ignored by Git.

`frontend/` is a Vite + React + TypeScript dashboard. Place reusable UI in
`frontend/src/components/`, API calls in `src/api.ts`, shared types in
`src/types.ts`, and application state hooks beside `src/useRun.ts`.

## Build, Test, and Development Commands

Use Python 3.11+ and Node 18+.

```bash
cd backend && ../venv/bin/python -m uvicorn app.main:app --port 8000
cd backend && AZ_PROVIDER=mock AZ_REVEAL_DELAY_S=0 ../venv/bin/python -m pytest -q
cd frontend && npm install && npm run dev
cd frontend && npm run build
```

On Windows, replace `../venv/bin/python` with `../venv/Scripts/python.exe`.
The mock provider keeps tests and local demos offline and deterministic. The
frontend dev server proxies API requests to the backend; `npm run build` runs
TypeScript checking before producing `frontend/dist/`.

## Coding Style & Naming Conventions

Match existing code. Python uses four-space indentation, type annotations,
`snake_case` functions/modules, `PascalCase` classes, and async endpoints where
I/O is involved. Keep the Verdict Engine deterministic and provider-independent.
TypeScript uses two-space indentation, semicolons, `PascalCase` component files
and exports (for example, `VerdictPanel.tsx`), and `camelCase` functions and
variables. No formatter or linter is configured; avoid drive-by reformatting.

## Testing Guidelines

Tests use `pytest` with `pytest-asyncio` (`asyncio_mode = auto`) and belong in
`backend/tests/` as `test_<feature>.py`. Add focused regression tests whenever
changing verdict calculations, persona diversity, or revision behaviour. Run
the mock-provider command above before submitting changes. The frontend has no
test runner configured, so validate UI work with `npm run build` and a local
browser check.

## Commit & Pull Request Guidelines

The Git history currently contains only the initial commit, so no established
commit convention exists. Use concise imperative subjects, such as
`Add persona validation` or `Fix rerun status update`. Keep commits scoped.
PRs should explain the user-visible or API impact, list validation performed,
link related issues when applicable, and include screenshots or a short video
for dashboard changes. Never commit `.env`, API keys, generated SQLite files,
or produced audio.

## Configuration & Security

Copy `.env.example` to `.env` for local configuration. Prefer `AZ_PROVIDER=mock`
unless real model calls are required; store keys only in environment variables.
