# 🎧 Audience Zero

**A synthetic test audience that predicts where an episode loses its listeners — before publish, not after.**

**Track:** P5 Creator Superpowers → *Audience Simulator* (with the *Cliffhanger
Optimizer* statement absorbed as the Binge Probability metric).

Paste an episode script (or upload produced audio). Six contrastive listener
personas each read the episode and score every beat. A deterministic Verdict
Engine aggregates their judgment into a predicted retention curve, a **Binge
Probability** (how likely a listener hits play on the next episode, driven by
the final-beat hook), highlights the weakest beat, and speaks the panel's
critique out loud. One click rewrites that beat into fully-produced audio;
re-run the panel to see the lift.

> *"Film studios test-screen for months. Audio studios ship a new episode every day — completely untested. This is their test audience."*

This is a complete, runnable implementation of the **Audience Zero build plan &
system design**. It runs **fully offline out of the box** (no API key, no
ffmpeg) via a deterministic mock provider, and switches to real OpenAI
LLM/STT/TTS automatically when a key is present.

---

## Quickstart

Prerequisites: **Python 3.10+**, **Node 18+**. A venv with backend deps is
already provisioned one directory above `audience-zero/` (`../venv`); if
you're starting fresh, recreate it (see [Fresh setup](#fresh-setup)).

### 1. Backend (terminal 1)

```bash
cd backend
# seed the cached golden-path demo run (optional but recommended for demos)
../venv/bin/python scripts/seed_demo.py
# start the API gateway
../venv/bin/python -m uvicorn app.main:app --port 8000
```
> On Windows the interpreter is `..\venv\Scripts\python.exe`. The venv is not
> part of this git repo — it lives one directory above `audience-zero/` — see
> [Fresh setup](#fresh-setup) if you're starting from scratch.

### 2. Frontend (terminal 2)

```bash
cd frontend
npm install      # first time only
npm run dev
```

Open **http://localhost:5173**. The dashboard header shows the active engine
(`mock` amber / `openai` green). Load a sample script, hit **Run Panel**, and
watch the golden path.

### Enable real OpenAI models (optional)

```bash
cp .env.example .env
# set AZ_OPENAI_API_KEY=sk-...   (or export OPENAI_API_KEY)
```
Everything else is identical — every external dependency sits behind an
interface, so the mock and OpenAI paths are interchangeable.

---

## The golden demo path

1. **Upload input** — paste a script (primary) or upload produced audio (STT).
2. **Six personas come alive** — attention curves draw progressively across the
   episode timeline; drop-point markers appear.
3. **Panel verdict** — aggregate predicted-retention curve, weakest beat
   highlighted, headline claim (*"predicted 71% drop at beat 7"*), personas
   speak their critique in their own cast voice.
4. **Fix the weakest beat** — scene rewritten from the persona critiques, played
   back as fully-produced audio (multi-voice + music bed + optional SFX).
5. **Re-run the panel** — before/after curve overlay, the lift made visible.
6. **Kicker** — hand it any script for a live run.

The **magic moment**: six curves dipping in unison at the boring beat while a
persona says, out loud, *"Too much recap — I'd skip here."*

---

## Producer workflow (v2)

The app is now a full producer workflow, not just a single-run tool. It is built
on a **frozen `AnalysisRun` contract** — `verdict + confidence · evidence_spans[]
· diagnostics[] · revision_variants[] · run_manifest · calibration_summary` —
with a **Project → Episode → Version → AnalysisRun → RevisionVariant** hierarchy.

A producer can:
- **Navigate** projects → episodes → versions → runs (`#/`, `#/project/:id`,
  `#/episode/:id`, `#/run/:id`), with full history that survives restarts.
- **Inspect a drop with evidence** — the Evidence Timeline shows a beat-time
  ruler, evidence ticks, persona filters, issue chips, and a transcript that
  highlights the exact spans (recap phrases, crowded casts, weak hooks) that
  triggered each drop, mapped to playback time (click-to-seek for audio versions).
- **See how trustworthy it is** — panel confidence, agreement, and a
  disagreement band drawn under the curve.
- **Choose a revision** — the Revision Lab compares the original beat against
  proposed variants, accept/reject with notes, and re-run to see the lift.
- **Collaborate** — comment on, assign, and resolve diagnostics.
- **Share a report** — an unguessable read-only link (`#/shared/:token`), a
  one-paragraph producer summary, and a **PDF export**.
- **Job UX** — queued/running/failed/complete with reconnectable SSE, a retry
  button, and a fallback notice when personas degrade to the deterministic scorer.
- **AI-audio disclosure** — every generated clip carries an AI-generated /
  voice-consent badge.

- **Calibration** — attach the episode's real post-publish retention (paste
  per-beat numbers or upload) or **simulate a sample**; the run then shows a
  predicted-vs-actual overlay with mean-absolute-error and correlation, and a
  calibration-state chip. This is the "your data makes it sharper" flywheel.
- **Voice consent** — the AI-audio disclosure is settable per revision
  (synthetic / consented / pending / unknown) for when a real voice is swapped in.
- **Model-enriched (with an OpenAI key)** — the analysis adds model-cited
  evidence spans (`source: "model"`) on the weakest beat, and the report summary
  can be AI-polished on demand ("✨ Polish with AI"). Both fall back to the
  deterministic path and never block a run.
- **Custom test personas** (`#/personas`) — add your own listener to the panel:
  name it, give it a category, write its persona prompt, or **draft it in a
  multi-turn chat**. Saved personas join the roster and **auto-participate in
  every new analysis** — appearing in the attention graph, persona cards,
  verdict, evidence, and sweep. With an OpenAI key the model reads the custom
  prompt so it scores distinctively; offline it uses a neutral profile (the app
  says so). Custom personas can be deleted from the library (`#/personas`).
- **Per-project panel selection** — each project has its own **Test panel**: a
  persistent on/off switch per persona (built-in and custom). Only the enabled
  ones test that project's episodes, and the selection sticks per project (new
  projects default to all on; at least one must stay enabled). Toggling a persona
  in Project A doesn't affect Project B.

Everything stays **mock-first / offline**; the dev SQLite DB is disposable
(re-seed with `scripts/seed_demo.py`). Deep-links: `#/run/:id`,
`#/run/:id?sweep=1` (auto-run Population Sweep), `#/shared/:token`.

---

## Time-travel branching & parallel universes (v3)

Two related but distinct branching systems, plus a story bible that threads
memory between them.

### Story Tree — rewrite one episode from any beat (`#/tree/:episodeId?version=:id`)

Open any version's **"Explore branches →"** link from its Episode page. The
first visit seeds a linear spine of `StoryNode`s (one per existing beat,
idempotent — safe to revisit). Click any node, type free-form text ("Kael
abandons the gate and flees into the forest"), and **Branch from here**
generates a new sibling node — the original beat and every other branch stay
untouched, so exploring three different "what happens next"s from the same
point never overwrites the other two. Each node carries a full, independent
copy of character state (memory / emotional state / relationships); branching
never shares or mutates that state across siblings (copy-on-write). A separate,
non-blocking consistency pass flags contradictions against everything
established up that branch's own ancestor chain — it only ever warns, never
retries or blocks. When a branch is ready to actually be scored by the persona
panel, **materialize** it: this walks the branch's ancestor chain into an
ordinary `Version` and hands it to the *exact same* `/versions/{id}/analyze`
pipeline every other version uses — no special-cased scoring path.

### Universe Graph — episodes across a whole series (`#/project/:id/matrix`, linked from a project's page)

Episodes **grow in a straight line by default** — adding a new episode to a
project auto-chains its first version onto whatever the project's current
"main" line last ended on. Nothing needs to be tagged or assigned for that
common case.

A "universe" (a named parallel timeline) is created automatically the moment
an *existing* episode is **altered** — i.e. you add a second version to an
episode that already has one. That alteration itself is the branch point: the
new version auto-mints a universe and inherits the original's own parent, so
the two versions become true siblings fanning out from whichever episode came
before. **No manual "assign this version to a universe" step exists in the
normal flow** — the graph reflects branch structure that already exists in
your version history.

The graph (`UniverseGraphCanvas`) renders every version as one tree via
`parent_version_id` — not fixed per-universe lanes — so a version with three
children draws three edges fanning out from one node, and a version with none
is a single line falling straight down. Click any solid node to **open its
episode** or explicitly **branch a brand-new universe from it** (an optional
name — auto-numbered if left blank — plus an optional free-form instruction,
either AI-generates an opening scene or hands you off to paste a script
yourself). Click a dashed **ghost node** — the one open next-step under any
line that hasn't continued yet — to grow *that same* line forward instead of
starting a new one.

**So: to continue into the next episode of a specific branch**, open the
project's Universe Graph, find that branch's leaf node (its dashed ghost node
one row below is the "next episode" slot), click the ghost node, and either
generate an opening scene or paste a script. To *fork yet another* alternate
future from an existing episode instead, click the solid node itself and use
"Branch a new universe from here."

### Story Bible (`memory.md`) — theme, character roles, and constraints across episodes

A `Version`'s story bible is a structured, LLM-filled spec (`theme`,
`characters: [{name, role, behavior_notes}]`, `constraints`) rendered to
markdown — generated on demand from a version's Episode page ("📖 Generate
story bible"), **never automatically** (no surprise paid calls). It's a
separate, higher-level artifact from the Story Tree's per-character state —
both feed into generation, but the bible captures cross-cutting narrative
rules a single character's memory doesn't. Every version's bible is
immutable and fresh — a child's bible is generated *from* its parent's, never
an edit to it. Continuing a universe automatically carries the parent's bible
forward into the child in the same action, but **only if the parent already
has one** — a project that never opts into story bibles never pays for them.

## Architecture

Maps 1:1 to the system design. Contracts over coupling; personas are data, not
code; LLMs judge, deterministic code decides; computation is real, streaming is
theatre; every external dependency sits behind an interface.

```
Dashboard (React + Vite + Recharts, SSE)
        │  REST + Server-Sent Events
API Gateway (FastAPI + async event bus)  ── app/main.py, event_bus.py
        │
Ingestion ─► Beat Segmenter ─► Panel Orchestrator ─┬─► Persona Agent Runtime ×6
   (script | audio→STT)         (asyncio fan-out)   │      (per-agent model/prompt)
        │                                            ▼
        │                                    Verdict Engine  (pure, deterministic)
        │                                            │
        │                                    Revision Service ─► Audio Production
        │                                            │              (casting→TTS→mix)
        ▼                                            ▼
                              Session Store (SQLite)  ◄── cached, replayable runs
```

| Component | File |
|---|---|
| Data contracts (frozen Day 0 + v3 additions) | `backend/app/contracts.py` |
| Coordinator (wires every service; API + tests both drive this) | `backend/app/pipeline.py` |
| Persona Registry (`personas/*.yaml`) | `backend/app/services/persona_registry.py` |
| Ingestion + Beat Segmenter | `backend/app/services/ingestion.py` |
| Persona Agent Runtime | `backend/app/services/persona_runtime.py` |
| Panel Orchestrator (fan-out/fan-in) | `backend/app/services/orchestrator.py` |
| **Verdict Engine** (pure, unit-tested) | `backend/app/services/verdict_engine.py` |
| Revision Service | `backend/app/services/revision.py` |
| Audio Production (TTS + WAV mix) | `backend/app/services/audio_production.py` |
| **Story Tree** — beat-level time-travel branching | `backend/app/services/story_tree.py` |
| **Memory Bible** — renders a `MemorySpec` → `memory.md` (pure, no LLM call) | `backend/app/services/memory_bible.py` |
| Session Store (SQLite — projects/episodes/versions/universes/runs/story_nodes/custom_personas) | `backend/app/services/session_store.py` |
| Event bus + SSE | `backend/app/event_bus.py`, `events.py` |
| Providers (mock / OpenAI) | `backend/app/providers/` |

### Providers

Every external dependency (LLM judgment, STT, TTS, mixing) is a `Protocol`
(`providers/base.py`), including the v3 story-branching operations —
`advance_story` (one combined call: new scene text + updated character
states), `check_consistency` (separate LLM-as-judge pass), `extract_character_state`
(fold an already-written beat into cumulative state), and `generate_memory`
(story-bible spec extraction):

- **mock** — deterministic heuristics (`providers/heuristics.py`) produce
  genuinely divergent persona judgment with zero network; audio is synthesized
  with the stdlib `wave` module (distinct timbre per voice). No key, no ffmpeg.
  The same heuristic philosophy covers branching — coarse but deterministic
  character-state folding and antonym-cue consistency checks.
- **openai** — real `gpt-4o`/`gpt-4o-mini` structured calls, `gpt-4o-transcribe`
  STT, and TTS. Degrades gracefully to the heuristic if a call fails, so one
  flaky agent never blocks the panel — the same fallback covers every v3
  operation too.

### The six personas (contrastive by design)

| Persona | Archetype | Model | Trait |
|---|---|---|---|
| Meera | Binge romance listener | gpt-4o | High emotional-beat appetite; tolerates slow burn |
| Arjun | Skip-happy commuter | gpt-4o-mini | 90-second patience; punishes recap hard |
| Kavya | Thriller purist | gpt-4o | Rewards tension; punishes unearned twists |
| Dev | Casual multitasker | gpt-4o-mini | Loses the thread past 3 characters/beat |
| Ananya | Genre-savvy critic | gpt-4o | Detects tropes; small weight, loud verdict |
| Ravi | Cliffhanger addict | gpt-4o-mini | Scores almost entirely on the final hook |

Scaling the built-in roster is six more YAML files; scaling per-project is a
custom persona (`#/personas`, DB-backed, no file edit) plus a toggle in that
project's Test panel. Either way, the orchestrator never learns persona
internals — every persona still emits the identical `PersonaReport` schema.

---

## Tests

The divergence acceptance test (**the #1 product risk**) and the Verdict Engine
unit tests both run offline:

```bash
cd backend
AZ_PROVIDER=mock AZ_REVEAL_DELAY_S=0 ../venv/bin/python -m pytest -q
```

`AZ_PROVIDER=mock` is required, not cosmetic: `.env` carries a real key and
`AZ_PROVIDER=auto`, so an unguarded run resolves to the OpenAI provider.

`tests/conftest.py` points every test at a throwaway temp-directory database
(and audio dir) via an autouse fixture — `get_settings()` is a cached
singleton whose `db_path` otherwise defaults to the same file the live dev
server reads from, so without this a test run would silently write fixture
projects into your real database.

- `test_verdict_engine.py` — locks the headline maths (aggregate curve,
  retention model, weakest-beat, before/after lift, degraded-panel safety).
- `test_divergence.py` — proves personas aren't clones, skip points diverge, the
  deliberately-boring-middle script dips in the middle, the thriller purist
  prefers thrillers and the romance binger prefers romance, and runs are
  deterministic.
- `test_story_tree.py` — cumulative character state along a seeded spine,
  copy-on-write isolation between sibling branches, non-blocking consistency
  warnings, and the materialize seam into the ordinary analyze pipeline.
- `test_universes.py` — episodes growing linearly by default, altering an
  episode auto-branching a new universe, forking one version into several
  distinct universe-children (the actual "one node, N edges" shape), and the
  project matrix aggregation.
- `test_memory_bible.py` — story-bible generation at the root, bundled
  generation on continuation (only when the parent opted in), and a child's
  bible inheriting the parent's characters/theme without mutating it.

---

## Deploy to Databricks Apps

**Live:** https://audience-zero-7474646075169951.aws.databricksapps.com — verified
end to end with real OpenAI models on 2026-07-25. Step-by-step runbook, Free
Edition quotas and failure fallbacks: [`DEPLOY_RUNBOOK.md`](DEPLOY_RUNBOOK.md).

One app, one process: FastAPI serves the API under `/api` and the built React
bundle at `/`. `backend/` is the deployed source root — `app.yaml`,
`requirements.txt`, `app/` and the generated `static/` all sit there, and
`app/server.py` is the ASGI entry point (`app/main.py` stays the local-dev entry
behind the Vite proxy).

```bash
# once: CLI + auth
databricks auth login --host https://<workspace-url> --profile hackathon
databricks current-user me --profile hackathon        # gate: prints your user JSON

# once: the OpenAI key as a secret (the value is never echoed)
databricks secrets create-scope audience-zero -p hackathon
databricks secrets put-secret audience-zero openai_api_key -p hackathon
# then App → Edit → Resources → add Secret resource named `openai_api_key`
# (scope audience-zero, key openai_api_key) — the name must match app.yaml's valueFrom

# every deploy: build → sync → deploy → print the verification URLs
./scripts/deploy_databricks.sh
DRY_RUN=1 ./scripts/deploy_databricks.sh     # show what would sync, deploy nothing
SKIP_BUILD=1 ./scripts/deploy_databricks.sh  # backend-only change, reuse the bundle
```

Verification gates (open in a browser — the app URL sits behind Databricks
OAuth, so `curl` from outside needs a bearer token):

| Check | URL | Pass |
|---|---|---|
| API up | `/api/health` | 200 `{"status":"ok","provider":…}` |
| UI served | `/` | dashboard loads |
| Secret injected | `/api/debug/env-check` | `openai_key_present: true`, `db_writable: true` |
| Audio mixer | `/api/debug/ffmpeg` | any result — the mixer is stdlib `wave`, ffmpeg is never required |
| SSE not buffered | `/api/debug/sse-counter` | ten ticks ~1/second, **not** one burst at the end |

If the SSE ticks arrive in a single burst, a proxy is buffering: switch the
dashboard to 1s polling of `GET /api/runs/{id}` (visually identical) and keep the
SSE path behind a flag.

State on the deployed app is **ephemeral** — `AZ_DB_PATH` and `AZ_AUDIO_DIR`
point at `/tmp` because the synced source tree is read-only, so a restart clears
run history and produced WAVs. Re-seed the cached golden run when that matters.

### Rollback

Localhost is the drilled fallback; it needs no Databricks at all:

```bash
cd backend && AZ_PROVIDER=mock ../venv/bin/python -m uvicorn app.server:server --port 8000
# then open http://localhost:8000  (same single-process topology as the deployed app)
```

Logs for a misbehaving deploy: `databricks apps logs audience-zero -p hackathon`.

---

## API surface

**Core golden path**

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/episodes` | JSON `{title,text}` **or** multipart audio → ad-hoc Version + Beats |
| `POST` | `/versions/{id}/analyze` | Trigger a run (async) → `{run_id}` |
| `GET` | `/runs/{id}/events` | **SSE** telemetry stream |
| `GET` | `/runs/{id}` | Full `AnalysisRun` |
| `POST` | `/runs/{id}/revise?target=weakest\|ending` | Fix the weakest beat (or strengthen the final beat) → RevisedScene + ProducedAudio |
| `POST` | `/runs/{id}/rerun` | Re-run with the fix → before/after (drop lift, or binge lift for an ending fix) |
| `POST` | `/runs/{id}/sweep?n=200` | Population Sweep → drop-point histogram (§2.10 stretch) |
| `GET` | `/scripts`, `/runs`, `/health` | Samples / history / status |
| `GET` | `/episodes/{id}` | Full episode (versions + runs) — powers deep-link replay |
| `GET` | `/audio/{file}` | Serve a produced/verdict WAV |

**Projects, episodes, personas**

| Method | Path | Purpose |
|---|---|---|
| `POST`/`GET` | `/projects` | Create / list projects |
| `GET` | `/projects/{id}` | Project + its episodes |
| `POST` | `/projects/{id}/episodes` | New episode (script or audio) — auto-chains onto the project's main timeline unless forking |
| `POST` | `/episodes/{id}/versions?parent=&universe_id=` | Add a version to an existing episode ("altering" it auto-branches — see below) |
| `GET` | `/personas` | Full library (built-in + custom), plain |
| `GET` | `/projects/{id}/personas` | Library with **this project's** enabled state |
| `POST` | `/projects/{id}/personas/{pid}/toggle` | Enable/disable a persona for this project only |
| `POST`/`DELETE` | `/personas`, `/personas/{id}` | Create / delete a custom persona |
| `POST` | `/personas/chat` | Multi-turn persona designer → `{reply, draft}` |

**Time-travel branching (one episode, beat-level) — see `#/tree/:episodeId?version=:id`**

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/versions/{id}/tree/seed` | Fold an existing version's beats into a linear `StoryNode` spine (idempotent) |
| `GET` | `/versions/{id}/tree` | All nodes for that version's tree |
| `GET` | `/nodes/{id}` | One node |
| `POST` | `/nodes/{id}/branch` | `{instruction}` → a new sibling node continuing from here (free-form, never edits history) |
| `POST` | `/nodes/{id}/materialize` | Turn a node's ancestor chain into a real `Version` → feed it into `/versions/{id}/analyze` unchanged |

**Cross-episode parallel universes — see `#/project/:id/matrix`**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/projects/{id}/matrix` | `{universes, episodes, versions}` — everything the graph needs in one call |
| `GET`/`POST` | `/projects/{id}/universes` | List / (rarely) explicitly create a universe |
| `POST` | `/versions/{id}/universe` | Explicit assignment (legacy path — branching is normally automatic, see below) |
| `POST` | `/versions/{id}/continue` | `{instruction?, new_universe_name?}` — continue this version's own universe forward, or **fork** a brand-new one from it |
| `POST` | `/versions/{id}/memory` | Generate/refresh this version's story-bible (`memory.md`) from its parent's |

The dashboard also supports **deep-link replay**: open `/?run=<run_id>` to load
any persisted run as a static view. In dev, point the proxy at a non-default
backend with `VITE_PROXY_TARGET=http://localhost:8020 npm run dev`.

---

## Project structure

```
z1hackathon/
├── venv/                    # Python environment — one level ABOVE the repo
└── audience-zero/           # ← this git repo
    ├── backend/             # ← the Databricks Apps source root
    │   ├── app.yaml         # Apps entry config (command + env, no secrets)
    │   ├── app/             # FastAPI app, services, providers, contracts
    │   │   ├── main.py      # API gateway (local dev entry)
    │   │   ├── server.py    # single-process entry: /api + static bundle
    │   │   ├── pipeline.py  # coordinates every service — the one class the API/tests drive
    │   │   └── services/
    │   │       ├── session_store.py  # SQLite (projects/episodes/versions/universes/
    │   │       │                     #   runs/story_nodes/custom_personas/...)
    │   │       ├── story_tree.py     # time-travel branching (beat-level, one episode)
    │   │       ├── memory_bible.py   # renders a version's MemorySpec → memory.md
    │   │       └── ...      # ingestion, orchestrator, verdict_engine, revision, ...
    │   ├── personas/        # 6 built-in persona YAML configs (data, not code)
    │   ├── data/scripts/    # demo + 3 calibration scripts
    │   ├── scripts/seed_demo.py # pre-cache the golden run
    │   ├── static/          # built dashboard — generated, uncommitted, but
    │   │                    #   deliberately NOT gitignored: `databricks sync`
    │   │                    #   honours .gitignore and would skip the bundle
    │   ├── tests/           # conftest.py (isolated temp DB) + verdict/divergence/
    │   │                    #   story-tree/universes/memory-bible tests
    │   ├── requirements.txt     # runtime deps (fastapi/uvicorn unpinned for Apps)
    │   └── requirements-dev.txt # + pytest
    ├── frontend/src/
    │   ├── components/
    │   │   ├── Sidebar.tsx, Header.tsx      # persistent nav shell
    │   │   ├── ProjectsView, ProjectView, EpisodeView, RunView
    │   │   ├── PersonasView.tsx             # custom persona library + chat designer
    │   │   ├── StoryTreeView, StoryGraphCanvas     # time-travel branching UI
    │   │   └── UniverseMatrixView, UniverseGraphCanvas  # cross-episode branching UI
    │   └── useNav.ts        # hash routes: /, /personas, /project/:id,
    │                        #   /project/:id/matrix, /episode/:id, /tree/:id, /run/:id
    ├── scripts/deploy_databricks.sh
    └── plan.md              # the original build plan
```

## Fresh setup

```bash
# venv sits one level above this repo, not inside it
python3 -m venv ../venv
../venv/bin/pip install -r backend/requirements-dev.txt   # macOS/Linux
# ..\venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt   # Windows
cd frontend && npm install
```

---

## Notes & improvements over the plan

- **Runs with zero configuration.** The mock provider makes the entire golden
  path (including audible multi-voice produced audio) work with no API key and
  no ffmpeg — the plan's "everything behind an interface, all mockable"
  principle taken to its logical, demo-safe conclusion.
- **Graceful degradation is real, not aspirational.** A failed/slow agent drops
  the panel to N−1; a malformed model response falls back to the deterministic
  heuristic; the Verdict Engine tolerates a partial panel.
- **Deterministic replay.** Cached runs persist to SQLite with pre-generated
  audio, so on-stage steps replay instantly and identically to a live run.

### P5 scope (§2.10)

- **Binge Probability** — a deterministic headline metric on `PanelVerdict`:
  final-beat hook strength, binge-weighted across personas (Ravi highest), shown
  as a gauge next to the verdict. Answers the *Cliffhanger Optimizer* statement.
- **Strengthen ending** — a second fix action that rewrites the **final** beat to
  raise Binge Probability (never lowers it); the before/after then reports the
  binge lift instead of the drop lift.
- **Population Sweep** — opt-in extrapolation from the 6 calibrated archetypes to
  ~200 sampled listeners (taste-seeds jittered by a stable hash) → a drop-point
  histogram. Answers the *"thousands of AI users"* framing. Deterministic in mock
  mode; the golden path never depends on it. Deep-link `/?run=<id>&sweep=1`
  auto-runs it.
