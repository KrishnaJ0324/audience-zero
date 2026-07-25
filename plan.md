# Audience Zero — Build Plan & System Design

**Event:** Zero to One Generative Media Hackathon (Pocket FM × OpenAI × Lightspeed) · IIM Bangalore · July 25–26, 2026 · 36 hours
**Track / Problem Statement:** **P5: Creator Superpowers → "Audience Simulator"** (official statement: *"thousands of AI users react to a story before it is released"*) — with the **"Cliffhanger Optimizer"** statement (*"predicts the probability of binge listening and suggests stronger endings"*) absorbed as a headline metric. Use this exact vocabulary in all pitch materials.
**Team:** 3 AI Engineers (Dev A, Dev B, Dev C — assign names before Friday)
**One-liner:** A synthetic test audience that predicts where an episode loses its listeners — before publish, not after.

> **Compliance rule for this plan:** Pre-written code is NOT allowed at this event. This week's build (Phase 0) is a **throwaway practice prototype** — never pushed, never copied. What travels to the venue: this document, persona system prompts, calibration scripts, casting notes, and muscle memory. All venue code is written fresh from hour 0.

---

## 1. Golden Demo Path (everything serves this)

1. Upload input — **paste script** (primary) or **upload produced audio** (secondary) → "Run Panel"
2. 6 personas come alive → attention curves draw progressively across the episode timeline, drop-point markers appear
3. Panel verdict → aggregate predicted retention curve, weakest beat highlighted, headline claim ("predicted 38% drop at beat 7"), 2–3 personas **speak** their critique in their own voice
4. One click: "Fix beat 7" → scene rewritten using persona critiques → plays back as **fully produced audio** (multi-voice + music bed + SFX)
5. Re-run panel → before/after curve overlay, lift visible
6. Kicker: judge hands us any script → live run

**Only the golden path must be real.** Everything off it is stubbed, cached, or cut without guilt.

**Magic moment:** six attention curves dipping in unison at the boring beat while a persona says, out loud, *"too much recap — I'd skip here."*

---

## 2. System Design

### 2.1 Design principles

1. **Contracts over coupling.** Every component communicates through typed Pydantic models. No component imports another's internals.
2. **Personas are data, not code.** Each persona is a config file (model, system prompt, skills, tools, voice, thresholds). Adding persona #7–12 = adding a file. The orchestrator never knows persona internals.
3. **LLMs judge, deterministic code decides.** All headline numbers come from a pure-function Verdict Engine, not from a model. Reproducible, unit-testable, defensible in Q&A.
4. **Computation is real; streaming is theatre.** Panel runs as parallel one-shot calls (~20–40s wall time); the dashboard animates results progressively. Never claim the animation is real-time inference.
5. **Every external dependency sits behind an interface.** STT, LLM, TTS, mixing — all swappable, all mockable, all cacheable.

### 2.2 Component architecture

```mermaid
flowchart LR
    UI[Dashboard\nReact + SSE] <--> GW[API Gateway\nFastAPI + Event Bus]
    GW --> ING[Ingestion Service\nscript | audio→STT]
    ING --> SEG[Beat Segmenter]
    SEG --> ORC[Panel Orchestrator\nfan-out / fan-in]
    REG[(Persona Registry\nconfig files)] --> ORC
    ORC --> PA[Persona Agent Runtime ×N\nper-agent model/prompt/tools]
    PA --> VE[Verdict Engine\ndeterministic, pure]
    VE --> REV[Revision Service]
    REV --> AUD[Audio Production Service\ncasting → TTS → mix]
    VE --> SS[(Session Store)]
    AUD --> SS
    SS --> GW
```

### 2.3 Components & responsibilities

| # | Component | Responsibility | Key interface | Owner |
|---|-----------|----------------|---------------|-------|
| 1 | **Ingestion Service** | Accept script text or audio file. Audio → STT (`gpt-4o-transcribe` / Whisper) with timestamps → transcript. Normalizes both inputs into one `Episode` object. | `ingest(source) -> Episode` | A |
| 2 | **Beat Segmenter** | Split episode into 10–15 beats (timestamped segments + one-line summaries). Single LLM call, structured output. | `segment(Episode) -> list[Beat]` | A |
| 3 | **Persona Registry** | Loads persona configs from `personas/*.yaml`. Validates schema. Hot-reload in dev. | `load() -> list[PersonaConfig]` | B |
| 4 | **Panel Orchestrator** | Fan-out: `asyncio.gather` one task per persona. Fan-in: collect `PersonaReport`s. Emits progress events. Retries + 60s timeout per agent; a failed agent degrades to N−1, never blocks the panel. | `run_panel(Episode, Beats, Personas) -> list[PersonaReport]` | A |
| 5 | **Persona Agent Runtime** | One agent = one call to its **own configured model** with its **own system prompt**; optional tools (genre knowledge lookup, prior-run memory). Enforced structured output. Internals opaque to the orchestrator. | `evaluate(Episode, Beats, PersonaConfig) -> PersonaReport` | B |
| 6 | **Verdict Engine** | **Pure deterministic function.** Aggregate curve (weighted mean), per-persona skip application, weakest-beat detection, headline metrics, before/after deltas. Zero LLM calls. Unit tests written first. | `judge(list[PersonaReport]) -> PanelVerdict` | A |
| 7 | **Revision Service** | Weakest beat + persona critiques → rewritten scene (LLM, structured output). One scene only — never the full episode. | `revise(Beat, critiques) -> RevisedScene` | B |
| 8 | **Audio Production Service** | Two jobs: (a) produce the revised scene — casting map → per-line TTS (distinct voices) → music bed + 1–2 SFX → ffmpeg mix; (b) render persona verdicts to speech in each persona's cast voice. | `produce_scene(RevisedScene) -> ProducedAudio`, `speak_verdict(PersonaReport) -> AudioClip` | B |
| 9 | **Session Store** | Persist runs, reports, verdicts, audio paths. Enables re-run comparison + instant replay of cached runs. SQLite. | CRUD on `PanelRun` | C |
| 10 | **API Gateway** | FastAPI. REST for commands, **SSE** for progress/telemetry events. Internal pub/sub event bus decouples computation from UI theatrics. | see §2.5 | C |
| 11 | **Dashboard** | React + Vite + Recharts. Progressive curve reveal, drop markers, persona cards with audio playback, before/after overlay. Dark mission-control aesthetic. | consumes SSE + REST | C |

### 2.4 Data contracts (Pydantic — freeze these on Day 0, everything else can drift)

```python
class Episode:      id, title, source_type: Literal["script","audio"], transcript, duration_s: float|None
class Beat:         index, start_s, end_s, summary, text
class PersonaConfig:id, name, archetype, model: str,          # e.g. "gpt-4o" | "gpt-4o-mini" — per-agent
                    system_prompt, tools: list[str], voice_id,
                    skip_threshold: int, weights: dict         # taste profile knobs
class BeatScore:    beat_index, engagement: int  # 0–100
class PersonaReport:persona_id, scores: list[BeatScore], skip_at_beat: int|None,
                    drop_reason, verdict_text, confidence: float
class PanelVerdict: aggregate_curve: list[float], weakest_beat: int, predicted_drop_pct: float,
                    per_persona_summary, headline: str
class RevisedScene: beat_index, new_text, change_rationale, casting: dict[speaker, voice_id]
class PanelRun:     id, episode_id, verdict, reports, produced_audio_path, parent_run_id  # parent → before/after
```

### 2.5 API surface (minimal by design)

```
POST /episodes                 # script text or audio upload → Episode + Beats
POST /episodes/{id}/panel      # trigger run → run_id (async)
GET  /runs/{id}/events         # SSE: agent_started, beat_scored, agent_done, verdict_ready, audio_ready
GET  /runs/{id}                # full PanelRun
POST /runs/{id}/revise         # fix weakest beat → RevisedScene + ProducedAudio
POST /episodes/{id}/panel?parent={run_id}   # re-run for before/after
```

### 2.6 The six personas (v1 roster — contrastive by design)

| Persona | Archetype | Model | Contrastive traits |
|---|---|---|---|
| Meera | Binge romance listener | gpt-4o | High emotional-beat appetite; tolerates slow burn; hates skipped relationship payoff |
| Arjun | Skip-happy commuter | gpt-4o-mini | 90-second patience; punishes recap hard; skips 40 pts earlier than Meera |
| Kavya | Thriller purist | gpt-4o | Rewards tension mechanics; punishes plot holes and unearned twists |
| Dev | Casual multitasker | gpt-4o-mini | Loses thread if >3 characters per beat; rewards clarity and re-hooks |
| Ananya | Genre-savvy critic | gpt-4o | Detects tropes and clichés; small audience weight, loud verdicts |
| Ravi | Cliffhanger addict | gpt-4o-mini | Scores episodes almost entirely on final-beat hook strength |

Per-agent model diversity is a feature (genuinely different judgment distributions) — but **all agents emit the identical `PersonaReport` schema**, or the Verdict Engine breaks. Scaling 6 → 12 later = six more YAML files.

**Divergence acceptance test (the #1 product risk, tested before any UI exists):** run 3 calibration scripts — (1) romance-heavy, (2) thriller-heavy, (3) deliberately boring middle. PASS = visibly divergent curves, different skip points, script 3's aggregate dips at the boring beats on every run. FAIL = fix prompts/weights now, not at hour 20.

### 2.7 Audio input & output (the "final product audio" decision)

- **Input:** audio is a first-class ingestion source. STT with timestamps → beats carry real `start_s/end_s`, so drop markers land on real playback time. Pitch upgrade: *"we test what listeners actually hear, not just what writers wrote."*
- **Output:** the revised scene is always delivered as produced audio (multi-voice, music, SFX). **Full-episode audio render is a stretch goal only** — one flag in the Audio Production Service, attempted only if Phase 4 finishes early.
- **Demo call:** the on-stage run uses a script input (deterministic); the audio-input path is shown pre-loaded ("here's one we ran on produced audio") unless rehearsals prove the live audio path is rock solid.
- v2 slide (do not build): prosody/pacing features from raw audio feeding persona judgment.

### 2.8 Caching & demo-safety strategy

- Every panel run is persisted; the **rehearsed demo script's run is cached** → on-stage steps 2–5 replay instantly and deterministically from the store while looking identical to a live run.
- Live API calls happen exactly once on stage: the judge-input kicker (step 6).
- All TTS assets pre-generated during rehearsal for the cached path.
- If wifi dies: entire golden path runs from cache + local audio files. If the laptop dies: backup screen recording (Phase 5, non-negotiable).

### 2.9 Trade-offs made explicit

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Orchestration | `asyncio.gather` + OpenAI SDK | LangGraph | 6 parallel one-shots + 1 chain need no graph; framework ceremony kills 36h builds; OpenAI-native optics at their event |
| Persona calls | 1 call/persona, all beats | per-beat calls (6×15=90) | 6 calls ≈ 30s vs minutes; beat-level granularity preserved in output schema |
| Headline numbers | Deterministic Verdict Engine | LLM-generated summary | Reproducible, unit-testable, survives "how is this computed?" in Q&A |
| Streaming | Progressive reveal of completed results | true token streaming | Identical audience experience, 10% of the engineering |
| Storage | SQLite | Postgres/Redis | One file, zero ops, survives process restarts for cached demo |
| Full-episode audio | Stretch flag | in golden path | Triples audio surface area; nobody asks for it in a 3-min demo |

### 2.10 P5 positioning & new scope items

- **Binge Probability (new headline metric, Verdict Engine):** final-beat hook score aggregated across personas (Ravi weighted highest) → `binge_probability: float` on `PanelVerdict`, displayed as a gauge next to the retention curve. Fix loop can target the final beat ("suggest stronger endings" — official wording). Cost: one engine field + one UI element.
- **Population Sweep (STRETCH FLAG, Phase 4 only, cut line #7):** ~200 async gpt-4o-mini calls with trait-seeds sampled around the 6 archetypes → drop-point distribution histogram. Answers the "thousands of AI users" wording. Golden path never depends on it.
- **Competitive framing (pitch language):** "Reactions are easy — predictions you can act on are the product." Differentiators vs. other Audience Simulator teams: beat-level telemetry, deterministic verdict engine, spoken verdicts, closed fix→regenerate→re-run loop, calibration flywheel.
- **"Why only 6?" defense:** 6 deeply differentiated, model-diverse, calibratable personas beat 1,000 shallow clones — a thousand copies of one taste is a crowd, not an audience. Then point at the Population Sweep histogram if built.

---

## 3. Phased Plan

### Phase 0 — Pre-event (now → Fri Jul 24) · all hands
**Goal: kill the two project-killing risks (persona sameness, audio mix) before the clock exists.**
- [ ] Verqa YC application submitted **by Thursday** (hard external deadline Jul 27 — do not carry it into the weekend)
- [ ] 6 persona YAMLs: prompts, weights, thresholds, models (B)
- [ ] 3 calibration scripts written; **divergence test PASSED** (B)
- [ ] Practice prototype spine built & thrown away — ingestion → panel → verdict → static curves (A, C) · *local only, never pushed, never reused*
- [ ] ffmpeg 4-track mix proven once: 2 voices + music duck + SFX (B)
- [ ] TTS voice casting: 6 persona voices + 3 character voices, noted in casting sheet (B)
- [ ] Demo episode script v1 written — with 3 planted weak beats the panel must catch (C)
- [ ] Dashboard layout sketch + Recharts spike (C)
- [ ] API keys/credits confirmed; fallback key ready (A)
- [ ] Event rules re-read: submission mechanics, video requirement, team check-in (C)

**Exit criteria:** divergence test green · mix plays · each dev has personally built their venue-day components once.

### Phase 1 — Hours 0–6 · Walking skeleton (ugly, end-to-end)
- A: FastAPI skeleton, contracts frozen, ingestion (script path), segmenter, orchestrator
- B: Persona runtime + 6 configs re-authored, structured outputs validated
- C: React shell, SSE client, static curve render from real JSON
- **Gate @ hour 6:** script in → 6 real reports → verdict → curves on screen. If red: cut audio-input path immediately, keep going.

### Phase 2 — Hours 6–16 · The theatre
- C: progressive reveal animation, drop markers, weakest-beat highlight, persona cards
- B: verdict TTS in cast voices, playable from cards
- A: Verdict Engine hardened + unit tests, session store, caching, audio-input ingestion (STT)
- **Gate @ 16:** golden path steps 1–3 demo-able and cool.

### Phase 3 — Hours 16–24 · Fix & re-run
- B: Revision Service + produced-audio scene (multi-voice, music, SFX)
- A: re-run flow, parent-run linkage, before/after payload
- C: comparison overlay, "Fix this beat" interaction
- **Gate @ 24:** full golden path 1–5 works end to end at least once.

### Phase 4 — Hours 24–27 · Polish demo path ONLY
- Rehearsal run cached · demo script v2 · visual polish on the six on-screen states · stretch flags (full-episode audio) only if all gates green
- **⛔ INTEGRATION FREEZE @ HOUR 27.** No new features. Wiring, fixing, polishing only. Put it on a phone alarm now.

### Phase 5 — Hours 27–36 · Performance
- [ ] **Backup screen recording of golden path** — first task after freeze, non-negotiable
- [ ] Submission drafted & submitted EARLY (video, repo, write-up, track tag) — then edited
- [ ] 6-slide deck: Hook → Problem → DEMO (60%+) → Why it's hard → Impact/what's-next → Team + ask
- [ ] 2 timed rehearsals out loud; one narrator + one demo driver, roles fixed
- [ ] Q&A drill (below) — every member can deliver the validity defense cold
- [ ] Sleep in shifts. Seriously.

---

## 4. Cut-Line Register (pre-agreed, executed without debate at 3am)

| Order | Cut | Trigger |
|---|---|---|
| 1 | SFX in regenerated scene (keep voices + music) | Phase 3 slipping |
| 2 | Audio-input path → pre-loaded example only | Phase 1 gate red |
| 3 | 6 spoken verdicts → 2 spoken + 4 text | TTS flaky |
| 4 | Live judge-input kicker → "prepared second script" | Latency > 60s or venue wifi bad |
| 5 | Before/after re-run → static comparison from cache | Phase 3 gate red |
| Never cut | Curves animating + 1 spoken verdict + 1 produced audio playback | — this IS the demo |

---

## 5. Demo Script Skeleton (v1 — refine in Phase 5)

```
Pre-load: dashboard open on cached blank state; demo script in clipboard;
          audio-input example run visible in history; backup video on desktop + phone.
0:00  HOOK — "Film studios test-screen for months. Audio studios ship a new
      episode every day — completely untested. We built their test audience."
0:20  Paste script → Run Panel
0:30  Curves draw. "Six listeners. Six different tastes. Watch beat 7."
      ★ Curves dip together → persona speaks: "too much recap, I'd skip here."
1:20  Verdict: "38% predicted drop at beat 7. Here's why, per listener."
1:35  Click Fix → produced scene PLAYS (voices + music). Room listens.
2:20  Re-run → overlay → "That's the lift, before anyone lost a listener."
2:40  KICKER — "Don't take our word. Someone hand us a script." (live run)
3:00  Close: "Creation is infinite now. Knowing what will land is the scarce
      thing. Audience Zero is your audience before your audience."
```

## 6. Q&A Defense Card (memorize)

- **"Why believe synthetic personas predict anything?"** → "Test screenings aren't perfectly predictive either — studios pay millions because *some* signal before release beats none. We claim cheap directional screening, not ground truth. And every real retention curve a studio feeds back calibrates the panel — your data makes it sharper, it's our moat, not our refutation."
- **"We have real listener analytics."** → "After publish. We're the layer before publish — where analytics can't exist yet. We complement your data; we don't compete with it."
- **"Is this dashboard real?"** → "Every number came from a live model call — hand us any script right now." (that's why the kicker exists)
- **"What's faked?"** → "The on-stage replay is cached from a real run for reliability; the live run you just gave us was end-to-end real. Full-episode audio render is roadmap."
- **"Business model?"** → "Per-seat SaaS for content teams at serialized-audio and AI-native studios; wedge is daily-episode QA, expansion is podcast networks and vertical drama apps."

## 7. Rules & Integrity

- No pre-written code enters the venue repo. Phase 0 prototype is deleted/archived-private and never referenced.
- Legal to bring: this plan, persona prompts & YAML *content re-typed at venue*, calibration scripts, casting sheet, demo script, deck skeleton.
- First venue commit = empty scaffold at hour 0. Commit early, commit often — a healthy history is itself evidence of a fair build.
