# Audience Zero — Databricks Apps runbook

## Live deployment (verified 2026-07-25)

| | |
|---|---|
| URL | https://audience-zero-7474646075169951.aws.databricksapps.com |
| Workspace | Databricks Free Edition — host comes from `DATABRICKS_PROFILE` in `~/.databrickscfg` |
| App / deployment | `audience-zero` — SUCCEEDED, RUNNING |
| Source path | `/Workspace/Users/<your-workspace-user>/audience-zero` |
| Provider | `openai` (Secret resource `openai_api_key` attached) |
| Service principal | the app's own SP, granted READ on scope `audience-zero` (id shown by `databricks apps get audience-zero`) |

Redeploy with `DATABRICKS_PROFILE=hackathon ./scripts/deploy_databricks.sh`.


One app, one process: FastAPI serves the API at `/api` and the built React bundle
at `/`. The deployed source root is **`backend/`** (`app.yaml`, `requirements.txt`,
`app/`, `static/`). Entry point: `app/server.py:server`.

Decisions already baked in: **ephemeral SQLite on `/tmp`** (no SQL warehouse, no
Delta) and the **OpenAI key as a Secret resource** (never a literal in `app.yaml`).

Everything in this repo is ready. What follows is only what needs your workspace.

---

## Path A — CLI (fastest: one command from you)

The CLI is already installed at `~/.local/bin/databricks` (v1.9.0). Only the OAuth
login is interactive.

### A1. Authenticate

```bash
databricks auth login --host https://<your-workspace-host> --profile hackathon
```

Opens a browser. Confirm it worked:

```bash
databricks current-user me --profile hackathon
```

### A2. Create the secret scope + key

The value is read from your terminal and never echoed.

```bash
databricks secrets create-scope audience-zero -p hackathon
databricks secrets put-secret audience-zero openai_api_key -p hackathon
databricks secrets list-secrets audience-zero -p hackathon      # gate: key listed
```

### A3. Deploy

```bash
cd audience-zero
./scripts/deploy_databricks.sh
```

It builds the dashboard, syncs `backend/` to `/Workspace/Users/<you>/audience-zero`,
creates the app if absent, deploys, then prints the status, URL and the five
verification URLs. Re-run it for every iteration (`SKIP_BUILD=1` for backend-only
changes, `DRY_RUN=1` to see the file list without deploying).

### A4. Secret resource — automatic

No UI step needed: the script attaches the Secret resource via
`apps update --json @scripts/app-resources.json` and grants the app's service
principal READ on the scope, **before** the deploy. Ordering matters — env vars are
injected at deploy time, so attaching the resource afterwards leaves the running
process without `OPENAI_API_KEY` until the next deploy.

The resource `name` must equal `valueFrom` in `app.yaml` (`openai_api_key`).

Equivalent UI path, if you ever need it: Compute → **Apps** → `audience-zero` →
**Edit** → **Resources** → **Add resource** → Secret, scope `audience-zero`,
key `openai_api_key`, resource name `openai_api_key`.

> Skipping A2/A4 is safe: the app resolves to the deterministic offline provider
> and the whole golden path still works, with the engine pill showing `mock`.

---

## Path B — Databricks UI only (git-backed, no local CLI)

Requires the deploy artifacts to be committed **and pushed**, including
`backend/static/` (the app pulls from git, so the built bundle must be in the repo).

### B1. Commit + push

```bash
cd audience-zero
git add backend/app.yaml backend/app/server.py backend/app/main.py \
        backend/requirements.txt backend/requirements-dev.txt \
        backend/static scripts/deploy_databricks.sh README.md DEPLOY_RUNBOOK.md
git commit -m "Add Databricks Apps single-process deployment"
git push origin main
```

### B2. Secret scope from a notebook

Databricks has no full secrets UI; a notebook against the SDK is the UI-only route.

```python
%pip install --upgrade databricks-sdk -q
dbutils.library.restartPython()
```

```python
import getpass
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
w.secrets.create_scope(scope="audience-zero")
w.secrets.put_secret(
    scope="audience-zero",
    key="openai_api_key",
    string_value=getpass.getpass("OpenAI key: "),
)
print([s.key for s in w.secrets.list_secrets(scope="audience-zero")])  # existence only
```

Clear the cell output and detach the notebook afterwards.

### B3. Create the app

Compute → **Apps** → **Create app** → name `audience-zero`.

Then **Edit**:
- **Resources** → add the Secret resource exactly as in **A4**.
- **Configure Git** → repo `https://github.com/vasan-rj/audience-zero.git`,
  reference **`main`** (must be a branch — tags never auto-deploy),
  source path **`backend`**, enable *Auto deploy on push*.
  Authorize the Git credential when prompted, then trigger **one manual redeploy** —
  auto-deploy only arms after that.

### B4. Grant the service principal READ on the secret scope

From the same notebook, using the service principal id shown on the app's page:

```python
from databricks.sdk.service.workspace import AclPermission
w.secrets.put_acl(scope="audience-zero",
                  principal="<app-service-principal-id>",
                  permission=AclPermission.READ)
```

---

## Verification gate — run after EVERY deploy

The app URL sits behind Databricks OAuth, so use a **browser** (external `curl`
gets 302/401 without a bearer token).

| # | Check | URL | Pass |
|---|---|---|---|
| 1 | API up | `/api/health` | 200 `{"status":"ok","provider":"openai"\|"mock"}` |
| 2 | UI served | `/` | dashboard loads, engine pill populated |
| 3 | Secret + writable state | `/api/debug/env-check` | `openai_key_present: true`, `db_writable: true`, `audio_writable: true`, `personas: 6` |
| 4 | Mixer | `/api/debug/ffmpeg` | any value — the mixer is stdlib `wave`; ffmpeg is never required |
| 5 | SSE not buffered | `/api/debug/sse-counter` | ten ticks ~1/second, **not** one burst at the end |
| 6 | Golden path | paste a sample script → **Run Panel** | curves draw progressively, verdict, Fix beat → audio plays, Re-run → before/after lift |

All six green = done. Any red → `references/troubleshooting.md` in
`context/databricks/databricks-apps-deploy/`, which maps each failure to its fallback.

Logs for a crash loop: `databricks apps logs audience-zero -p hackathon`, or the
app's **Logs** tab in the workspace UI.

### Known-red responses

- **`openai_key_present: false`** → the Secret resource *name* doesn't equal
  `valueFrom: openai_api_key` in `app.yaml`, or the service principal lacks READ.
- **SSE arrives in one burst** → a proxy is buffering. Switch the dashboard to poll
  `GET /api/runs/{id}` every 1s and animate from state diffs; visually identical.
  Keep the SSE path behind a flag.
- **404s on `/api/*` but `/` works** → a `StaticFiles` mount on `/` was registered
  before the API mount in `app/server.py`. The static mount must be last.
- **Crash loop on startup** → check for a hardcoded `--port` (the runtime injects
  `DATABRICKS_APP_PORT`), then for an import error from a dep missing in
  `requirements.txt`.
- **`[BUILD] [ERROR] No command to run and no Python file found. Please add a
  'command' field to your app.yml`** → a git-backed deployment was pointed at the
  **repo root**, which has no `app.yaml`. The source path must be **`backend`**.
  Observed live: it overrode a healthy SNAPSHOT deploy and left the app CRASHED.
- **UI is a version behind the API** (old hashed asset served, new endpoints
  answering) → the git-backed deploy ships the **committed** `backend/static/`.
  Rebuilding locally is not enough; the bundle has to be committed and pushed, or
  the git deploy keeps serving the stale one. Symptom: `/` references a different
  `assets/index-*.js` hash than `backend/static/assets/` holds locally. Diagnose:
  `curl -H "Authorization: Bearer $(databricks auth token -p hackathon | jq -r .access_token)" <url>/ | grep -oE 'assets/[^"]+'`

## Git-backed release flow (deploy on every commit)

One command per release — tests, build, secret guard, commit, push, deploy:

```bash
./scripts/release.sh "what changed"
```

It runs the backend tests (mock provider), rebuilds the dashboard into
`backend/static/`, refuses to continue if a key-shaped string is in any committable
file or `.env` stopped being ignored, commits, pushes, asserts the tree is clean and
`HEAD == origin/<branch>`, then deploys.

Git stays the source of truth: nothing is deployed that isn't a pushed commit.

```bash
NO_DEPLOY=1 ./scripts/release.sh "wip"     # commit + push only
SKIP_TESTS=1 ./scripts/release.sh "docs"   # skip the test gate
```

**Why it deploys in `local` mode, not `git` mode.** By the time it deploys,
everything is committed and pushed, so the working tree is bit-identical to
`origin/<branch>` — uploading it *is* deploying that commit, and it needs no
workspace Git credential. `apps deploy --source-code-path <clone>` **does not pull**:
the Apps git-integration clone at `<app>-git/` is refreshed only by a git-*triggered*
deploy (UI Redeploy, or auto-deploy on push). Deploying from a behind-clone silently
ships stale code — observed live: it re-shipped the v1 bundle against the v2 API.
Verify which bundle is actually live:

```bash
T=$(databricks auth token -p hackathon | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
curl -s -H "Authorization: Bearer $T" <app-url>/ | grep -oE 'assets/[^"]+'   # compare with backend/static/assets/
```

**True git-integration deploy** (Databricks pulls from GitHub itself) additionally
needs a workspace Git credential — `databricks git-credentials create` with a GitHub
PAT, since the repo is private — plus either auto-deploy on push or a UI Redeploy
click. Neither exists in this workspace today (`git-credentials list` and
`repos list` are both empty), which is exactly why the clone went stale.

**`backend/static/` must be committed.** Apps installs `requirements.txt` but never
runs `npm`, so a git deploy ships whatever bundle is in that commit. `release.sh`
rebuilds and commits it every time; git-mode `deploy_databricks.sh` warns when
`backend/` has uncommitted work, because that work will not be deployed.

Optional: **App → Edit → Configure Git → Auto deploy on push** makes any push
deploy itself. Convenient, but it bypasses the test and secret gates in
`release.sh` — and a push then silently replaces a local snapshot deploy.

### Two deployment modes, and how they fight

`apps deploy --source-code-path` (what the script does) creates a **SNAPSHOT**
deployment from a workspace path. Configuring **Git** on the app creates its own
deployments. Both target the same app, and the most recent one wins — so a push, or
a UI redeploy, silently replaces a snapshot. Pick one mode per demo:

- **SNAPSHOT (script)** — fastest loop, deploys exactly the local tree including a
  freshly built bundle. Nothing needs committing.
- **Git-backed** — source path must be `backend`, and `backend/static/` must be
  committed at the same commit as the code it serves.

`databricks sync --full` does not prune files the source no longer has, so old
hashed assets accumulate in the workspace path. Harmless — `index.html` names the
current ones — but don't read a stale `index-*.js` there as the live bundle.

---

## Rollback (drill it once before the demo)

Identical topology, no Databricks:

```bash
cd backend
AZ_PROVIDER=mock .venv/bin/python -m uvicorn app.server:server --port 8000
# http://localhost:8000
```

Stage rule: demo on the deployed URL; if it misbehaves twice, switch to localhost
without comment and keep the URL slide that proves it was deployed.

## Free Edition constraints (from `context/databricks/Databricks Hackathon Guide.pdf`)

Free Edition is serverless-only with fair-usage quotas; exceeding one can take the
affected compute offline for the rest of the day.

- **One workspace per account.** There is no shared/pre-provisioned host — the URL
  is whatever your Free Edition signup created. Pick the *final demo workspace*
  early and deploy there; teammates prototype in their own.
- **Up to 3 apps per account, and apps auto-stop after ~24h.** Restartable, but
  budget for one restart before judging — and note that a restart clears `/tmp`,
  so run history and produced WAVs vanish with it.
- **No GPU serving, no provisioned throughput.** Irrelevant here: nothing is
  self-served; the panel calls a hosted API or the offline heuristic.
- **Foundation Model APIs are OpenAI-protocol compatible** — a cheaper route than
  an external OpenAI key: set `AZ_OPENAI_BASE_URL` to
  `https://<workspace-host>/serving-endpoints`, set `OPENAI_API_KEY` to a
  Databricks token, and rename the `model:` field in each `personas/*.yaml` to a
  served endpoint (e.g. `databricks-meta-llama-3-3-70b-instruct`). Not wired by
  default: model names are per-workspace, and the model diversity across personas
  is a deliberate product feature that needs re-picking against whatever endpoints
  the workspace actually serves.
- **Deploy early and re-deploy often** is the guide's own advice; the deploy script
  is idempotent for exactly that.
- **Never commit tokens.** `/api/debug/env-check` reports key *existence* only.

## What is *not* deployed

- **Persistent storage.** `AZ_DB_PATH`/`AZ_AUDIO_DIR` point at `/tmp` because the
  synced source tree is read-only. Run history and produced WAVs reset on restart.
  Delta-backed persistence needs a serverless SQL warehouse, a Delta Session Store
  behind the existing interface, and UC grants — a deliberate follow-up, not part of
  deploying the current version.
- **The pre-seeded golden run.** `scripts/seed_demo.py` writes to the local SQLite
  file; on the deployed app it would be cleared by the next restart. Run the panel
  live on the deployed URL, or demo the cached run from localhost.
