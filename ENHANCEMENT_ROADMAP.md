# Audience Zero — Enhancement Roadmap

## Overall Product Idea

Audience Zero is a pre-release test audience for serialized audio. A creator
uploads an episode script or produced audio; differentiated synthetic listener
personas evaluate each story beat, predict where attention will drop, explain
the reason with supporting evidence, and suggest stronger alternatives before
the episode is published.

The product is not a replacement for post-release analytics. It is the
decision layer before analytics exist: a fast, repeatable screening process
that helps a creator reduce avoidable drop-offs, strengthen cliffhangers, and
compare revisions before spending money on production or distribution.

### Core User Journey

```text
Upload script/audio → inspect beat-level risks → review evidence and personas
→ select a constrained rewrite → re-run the panel → publish with confidence
→ import real retention → calibrate future predictions
```

## Overall Feature Goal

The north-star goal is **credible, actionable retention improvement before
release**.

For every episode, the product should answer five questions:

1. Where will listeners likely stop?
2. Which audience segment is affected?
3. What precise writing or audio evidence caused the prediction?
4. Which revision best addresses the issue without damaging the story?
5. Did the predicted risk align with real retention after release?

Success metrics:

- **Prediction quality:** decreasing error between predicted and observed
  drop points, tracked by genre and creator.
- **Actionability:** percentage of flagged issues with evidence and an
  accepted revision.
- **Creator value:** reduction in weak-beat drop rate for revised episodes
  versus their prior version or a comparable baseline.
- **Trust:** calibrated confidence labels; no unsupported claim that synthetic
  output is ground truth.
- **Speed:** a script analysis completes in a few minutes, with the initial
  verdict available quickly enough for an editorial session.

## Ideal Customer Profile (ICP)

### Primary ICP — Serialized-audio content teams

- **Who:** audio-drama studios, fiction podcast networks, vertical-drama
  publishers, and AI-native story studios producing episodes frequently.
- **Team:** 3–30 people across writers, story editors, producers, and content
  leads.
- **Volume:** at least 10 episodes per month, ideally with repeatable genres
  such as romance, thriller, drama, or comedy.
- **Pain:** they only learn about weak hooks, slow pacing, or confusing scenes
  after publishing; revisions are expensive once voice/audio production starts.
- **Buyer:** Head of Content, Creative Producer, Story Editor lead, or
  Content Operations lead.
- **Champion:** writer/editor who currently reads scripts manually and needs
  faster, evidence-backed feedback.
- **Trigger event:** a retention drop, launch of a new series, high production
  cost, a growing content slate, or a mandate to use AI responsibly.

### Secondary ICP — Independent high-output creators

Podcast fiction creators and small audio teams publishing weekly can use a
lighter self-serve plan: one show, a limited number of analyses, script-first
input, and shareable producer reports.

### Do Not Target First

- One-off hobby creators with no planned iteration cycle.
- General video, music, or text-only creators; their retention signals and
  workflows require different product design.
- Enterprise studios requiring deep SSO, data residency, or custom security
  before the calibration loop is proven.

## Product Packaging Hypothesis

| Tier | Customer | Included value |
| --- | --- | --- |
| Pilot | One studio/show | Script analysis, six personas, revision and report export |
| Team | Editorial team | Audio analysis, projects, collaboration, calibration dashboard |
| Enterprise | Multi-show studio | SSO, retention-data integration, custom personas, governance, SLA |

## Product Direction

Evolve Audience Zero from a compelling prototype into a calibrated,
evidence-led pre-release QA system for audio stories. The existing demo loop is
already strong: script/audio ingestion, persona scoring, retention and binge
metrics, revision, produced audio, re-run comparison, and a deterministic
population sweep.

The highest-value gaps are calibration against real listener retention,
evidence for every predicted drop, audio-native analysis, and production-ready
workflow controls.

## Priorities

| Priority | Feature | Outcome |
| --- | --- | --- |
| P0 | Real-retention calibration | Defensible, improving predictions |
| P0 | Evidence-linked diagnosis | Creators can act on each drop |
| P0 | Audio-native analysis | Score pacing, speakers, silence, and sound |
| P0 | Quality and security hardening | Reliable and safe production runs |
| P1 | Revision Lab | Compare multiple constrained fixes |
| P1 | Project workspace | Support teams, versions, and sharing |
| P1 | Cost and operations layer | Queue, retry, and measure model usage |
| P2 | Language and genre packs | Better regional and genre-specific analysis |
| P2 | Season planning | Arc-level retention and cliffhanger planning |

## Workstream 1 — Prediction Trust and Calibration

**Owner: You**

- Add v2 models: `EvidenceSpan`, `PredictionRecord`, `ObservedRetention`,
  `CalibrationReport`, `RunManifest`, and `ConfidenceBand`.
- Import post-release retention through CSV/API. Require episode ID, beat or
  timestamp, listeners started/reached, and completion rate.
- Build a calibration service that compares predicted and actual drops by genre
  and persona. Report MAE, Brier score, and calibration error.
- Persist prompt, model, provider, persona-set version, source hash, latency,
  and token/cost metadata for every analysis.
- Replace loose JSON-mode responses with strict schema-backed structured output
  while retaining the deterministic mock fallback.
- Build a model-evaluation corpus: planted boring middles, weak endings,
  prompt-injection inputs, multilingual scripts, and poor audio cases.
- Add API rate limits, upload validation, data deletion, and authentication
  before public deployment.

**Done when:** a creator can import retention from 20+ episodes, see
prediction-versus-actual accuracy, and uncalibrated outputs are labelled
“directional” rather than certain.

**Likely ownership:** `backend/app/contracts.py`, calibration and storage
services, feedback/metrics routes, and calibration tests.

## Workstream 2 — Audio Intelligence and Explainable Diagnosis

**Owner: Team Member 1**

- Preserve real audio timestamps during ingestion; add diarization/speaker
  turns where available instead of rescaling synthetic timestamps.
- Extract beat-level audio signals: speech rate, silence, speaker changes,
  overlap, loudness changes, music/SFX presence, and segment length.
- Attach an `EvidenceSpan` to every issue: timestamp, transcript quote,
  detected signal, affected personas, and confidence.
- Implement a stable issue taxonomy: recap overload, exposition density,
  character confusion, pacing drag, tonal mismatch, weak hook, dialogue
  monotony, and audio clarity.
- Add genre-aware scoring packs for romance, thriller, comedy, drama, and
  horror.
- Add sensitivity analysis to distinguish a universal drop from a
  persona-specific preference.
- Generate two or three constrained revisions such as “increase tension”,
  “reduce recap”, and “improve hook”, preserving characters and plot facts.
- Add deterministic tests using short WAV fixtures.

**Done when:** clicking a drop marker seeks to supporting audio/text evidence,
explains the problem in the issue taxonomy, and offers at least two bounded
revision options.

**Likely ownership:** audio-analysis and ingestion services, OpenAI audio
provider integration, WAV fixtures, and audio-analysis tests.

## Workstream 3 — Creator Workflow and Dashboard

**Owner: Team Member 2**

- Add projects, episodes, versions, analysis runs, and revisions to the
  dashboard workflow.
- Build an Evidence Timeline with waveform/transcript display, beat markers,
  persona filters, issue chips, and click-to-seek.
- Create a Revision Lab to compare the original with variants, accept/reject a
  change, add notes, and re-run the selected version.
- Show confidence, calibration state, persona disagreement, and
  prediction-versus-actual overlays.
- Add PDF exports, read-only share links, and a concise producer summary.
- Add comments, assignments, resolved issues, and revision history.
- Improve job UX with queued/running/failed/complete states, reconnectable SSE,
  retries, and clear fallback messages.
- Display AI-audio disclosure and voice-consent status wherever generated audio
  plays.

**Done when:** a producer can inspect a drop with evidence, choose a revision,
share a report, and return later without losing project history.

**Likely ownership:** `frontend/src/components/`, `useRun.ts`, `api.ts`, and
`types.ts`.

## Integration Rules

Freeze the API payload before feature work:

```text
AnalysisRun
  ├─ verdict + confidence
  ├─ evidence_spans[]
  ├─ diagnostics[]
  ├─ revision_variants[]
  ├─ run_manifest
  └─ calibration_summary
```

- Workstream 1 owns shared backend contracts and migrations.
- Workstream 2 publishes fixture payloads early.
- Workstream 3 builds against fixtures without waiting for live model work.
- Merge in order: contracts → audio/evidence → calibration → UI wiring.
- Preserve existing `/runs/{id}` behavior; introduce versioned `/v2/` routes for
  the new payload.

## Research-Backed Technical Choices

Use strict structured outputs for persona reports and evidence objects. They
enforce a supplied JSON Schema, which reduces invalid/missing fields and makes
schema failures detectable. [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

Treat model quality as an evaluated product surface. Dataset-based evals can
compare prompts/models and report criterion-level results and usage. [OpenAI Evals](https://developers.openai.com/api/docs/guides/evals)

Use speaker-aware speech-to-text and voice activity detection for timestamped
audio analysis rather than inferred timings. [OpenAI speech-to-text guide](https://developers.openai.com/api/docs/guides/speech-to-text)

Keep offline population experiments separate from live feedback; Batch API work
is asynchronous and better suited to experiments and calibration. [OpenAI Batch API](https://developers.openai.com/api/docs/guides/batch)

Treat scripts and audio as untrusted input. Defend against prompt injection,
validate model output, and avoid unnecessary model tool access. [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)

Before processing real customer episodes, add explicit retention/deletion
controls and consent handling. Voice creation requires consent recordings.
[OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data#default-usage-policies-by-endpoint)
and [voice consent API](https://developers.openai.com/api/reference/resources/audio/subresources/voice_consents/methods/list)

## Deliberately Defer

- Do not call the deterministic sweep “thousands of AI listeners” until it is
  calibrated against real outcomes.
- Do not add full-episode regeneration before scene-level revisions prove value.
- Do not clone creator or actor voices without explicit written consent and
  clear AI-audio disclosure.
- Do not prioritize a generic chat assistant over the core evidence-to-fix loop.
- Do not build a native mobile application before the desktop team workflow is
  proven.

## Testing Guide

### 1. Local Regression Checks

Run the existing offline backend suite before each pull request:

```bash
cd backend
AZ_PROVIDER=mock AZ_REVEAL_DELAY_S=0 ../venv/bin/python -m pytest -q
```

On Windows, use `../venv/Scripts/python.exe`. The suite must continue to prove
persona divergence, deterministic verdict maths, revision lift, and population
sweep behavior.

Build the frontend for TypeScript validation:

```bash
cd frontend
npm install
npm run build
```

### 2. New Automated Test Matrix

| Area | Required tests | Pass condition |
| --- | --- | --- |
| Contracts | Schema and API compatibility tests | Old run payloads still load; v2 fields validate |
| Personas | Divergence and genre preference fixtures | Personas do not collapse into identical curves |
| Calibration | Train/holdout retention fixtures | Metrics are computed only from held-out outcomes |
| Evidence | Timestamp/quote/audio-feature fixtures | Every material issue points to valid evidence |
| Revision | Character, length, and plot constraints | Revision changes only the requested beat safely |
| Security | Oversized files, bad MIME types, prompt injection | Uploads are rejected safely; prompts do not override instructions |
| Reliability | Provider timeout, malformed output, SSE reconnect | A partial panel degrades gracefully and can be resumed |
| UI | Component and end-to-end flows | Creator can run, inspect, revise, compare, and export |

### 3. Human Editorial Validation

Recruit 3–5 editors or experienced creators for a pilot. For each of 10–20
episodes, ask them to independently label the weakest beat and issue category
before seeing Audience Zero’s result. Then measure:

- agreement on weakest beat and issue type;
- whether the evidence is understandable and useful;
- whether a suggested revision is accepted or manually changed;
- time saved versus their normal review process; and
- observed retention after publishing, where available.

Do not tune prompts on the same episodes used to claim accuracy. Keep a
holdout set for reporting.

### 4. Release Gate

Ship a feature only when all of the following are true:

- offline tests and frontend build pass;
- the mock provider still works without network access;
- the happy path works with script and audio inputs;
- failures show a recoverable message, not a blank screen;
- no secret, generated audio, database, or customer episode is committed; and
- a creator can explain what the prediction means, what evidence supports it,
  and how confident the system is.
