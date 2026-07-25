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

Prerequisites: **Python 3.11+**, **Node 18+**. A `venv` with backend deps is
already provisioned in this repo; if you're starting fresh, recreate it (see
[Fresh setup](#fresh-setup)).

### 1. Backend (terminal 1)

```bash
cd backend
# seed the cached golden-path demo run (optional but recommended for demos)
../venv/Scripts/python.exe scripts/seed_demo.py
# start the API gateway
../venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```
> On macOS/Linux the interpreter is `../venv/bin/python`.

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

Everything stays **mock-first / offline**; the dev SQLite DB is disposable
(re-seed with `scripts/seed_demo.py`). Deep-links: `#/run/:id`,
`#/run/:id?sweep=1` (auto-run Population Sweep), `#/shared/:token`.

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
| Data contracts (frozen Day 0) | `backend/app/contracts.py` |
| Persona Registry (`personas/*.yaml`) | `backend/app/services/persona_registry.py` |
| Ingestion + Beat Segmenter | `backend/app/services/ingestion.py` |
| Persona Agent Runtime | `backend/app/services/persona_runtime.py` |
| Panel Orchestrator (fan-out/fan-in) | `backend/app/services/orchestrator.py` |
| **Verdict Engine** (pure, unit-tested) | `backend/app/services/verdict_engine.py` |
| Revision Service | `backend/app/services/revision.py` |
| Audio Production (TTS + WAV mix) | `backend/app/services/audio_production.py` |
| Session Store (SQLite) | `backend/app/services/session_store.py` |
| Event bus + SSE | `backend/app/event_bus.py`, `events.py` |
| Providers (mock / OpenAI) | `backend/app/providers/` |

### Providers

Every external dependency (LLM judgment, STT, TTS, mixing) is a `Protocol`:

- **mock** — deterministic heuristics (`providers/heuristics.py`) produce
  genuinely divergent persona judgment with zero network; audio is synthesized
  with the stdlib `wave` module (distinct timbre per voice). No key, no ffmpeg.
- **openai** — real `gpt-4o`/`gpt-4o-mini` structured calls, `gpt-4o-transcribe`
  STT, and TTS. Degrades gracefully to the heuristic if a call fails, so one
  flaky agent never blocks the panel.

### The six personas (contrastive by design)

| Persona | Archetype | Model | Trait |
|---|---|---|---|
| Meera | Binge romance listener | gpt-4o | High emotional-beat appetite; tolerates slow burn |
| Arjun | Skip-happy commuter | gpt-4o-mini | 90-second patience; punishes recap hard |
| Kavya | Thriller purist | gpt-4o | Rewards tension; punishes unearned twists |
| Dev | Casual multitasker | gpt-4o-mini | Loses the thread past 3 characters/beat |
| Ananya | Genre-savvy critic | gpt-4o | Detects tropes; small weight, loud verdict |
| Ravi | Cliffhanger addict | gpt-4o-mini | Scores almost entirely on the final hook |

Scaling 6 → 12 = six more YAML files. The orchestrator never learns persona
internals.

---

## Tests

The divergence acceptance test (**the #1 product risk**) and the Verdict Engine
unit tests both run offline:

```bash
cd backend
AZ_PROVIDER=mock AZ_REVEAL_DELAY_S=0 ../venv/Scripts/python.exe -m pytest -q
```

- `test_verdict_engine.py` — locks the headline maths (aggregate curve,
  retention model, weakest-beat, before/after lift, degraded-panel safety).
- `test_divergence.py` — proves personas aren't clones, skip points diverge, the
  deliberately-boring-middle script dips in the middle, the thriller purist
  prefers thrillers and the romance binger prefers romance, and runs are
  deterministic.

---

## API surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/episodes` | JSON `{title,text}` **or** multipart audio → Episode + Beats |
| `POST` | `/episodes/{id}/panel` | Trigger a run (async) → `{run_id}` |
| `GET` | `/runs/{id}/events` | **SSE** telemetry stream |
| `GET` | `/runs/{id}` | Full `PanelRun` |
| `POST` | `/runs/{id}/revise?target=weakest\|ending` | Fix the weakest beat (or strengthen the final beat) → RevisedScene + ProducedAudio |
| `POST` | `/runs/{id}/rerun` | Re-run with the fix → before/after (drop lift, or binge lift for an ending fix) |
| `POST` | `/runs/{id}/sweep?n=200` | Population Sweep → drop-point histogram (§2.10 stretch) |
| `GET` | `/personas`, `/scripts`, `/runs`, `/health` | Registry / samples / history / status |
| `GET` | `/episodes/{id}` | Full Episode (beats) — powers deep-link replay |
| `GET` | `/audio/{file}` | Serve a produced/verdict WAV |

The dashboard also supports **deep-link replay**: open `/?run=<run_id>` to load
any persisted run as a static view. In dev, point the proxy at a non-default
backend with `VITE_PROXY_TARGET=http://localhost:8020 npm run dev`.

---

## Project structure

```
tes-ready/
├── backend/
│   ├── app/                 # FastAPI app, services, providers, contracts
│   ├── personas/            # 6 persona YAML configs (data, not code)
│   ├── data/scripts/        # demo + 3 calibration scripts
│   ├── scripts/seed_demo.py # pre-cache the golden run
│   ├── tests/               # verdict + divergence tests
│   └── requirements.txt
├── frontend/                # React + Vite + Recharts dashboard
├── venv/                    # Python environment
└── plan.pdf                 # the original build plan
```

## Fresh setup

```bash
python -m venv venv
./venv/Scripts/python.exe -m pip install -r backend/requirements.txt   # Windows
# ./venv/bin/pip install -r backend/requirements.txt                    # macOS/Linux
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
