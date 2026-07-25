#!/usr/bin/env bash
# Deploy Audience Zero as a single-process Databricks App (FastAPI + built React
# bundle). Idempotent: safe to re-run for every iteration.
#
#   ./scripts/deploy_databricks.sh
#
# Two source modes — see DEPLOY_RUNBOOK.md "Two deployment modes":
#   SOURCE_MODE=local (default)  build locally, sync the tree up, deploy it.
#                                Fastest loop; nothing needs committing.
#   SOURCE_MODE=git              deploy from the app's Git-integration clone, so
#                                the deployed code is exactly a pushed commit.
#                                Requires backend/static/ committed at that commit.
#
# Env overrides:
#   DATABRICKS_PROFILE   ~/.databrickscfg profile      (default: hackathon)
#   APP_NAME             Databricks app name           (default: audience-zero)
#   SOURCE_MODE          local | git                   (default: local)
#   WORKSPACE_PATH       source-code path in workspace (default depends on mode)
#   SKIP_BUILD=1         reuse the existing backend/static bundle (local mode)
#   DRY_RUN=1            show what would sync, deploy nothing
set -euo pipefail

APP_NAME="${APP_NAME:-audience-zero}"
PROFILE="${DATABRICKS_PROFILE:-hackathon}"
SOURCE_MODE="${SOURCE_MODE:-local}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$REPO_ROOT/backend"   # app.yaml + requirements.txt + app/ + static/ live here

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Preflight"
command -v databricks >/dev/null || { echo "databricks CLI not on PATH"; exit 1; }
databricks --version
databricks current-user me -p "$PROFILE" -o json >/dev/null \
  || { echo "not authenticated: databricks auth login --host <workspace-url> --profile $PROFILE"; exit 1; }
USER_NAME="$(databricks current-user me -p "$PROFILE" -o json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["userName"])')"
case "$SOURCE_MODE" in
  local) WS_PATH="${WORKSPACE_PATH:-/Workspace/Users/$USER_NAME/$APP_NAME}" ;;
  # The Apps git integration clones the repo into <app>-git and refreshes it at
  # build time. The source path must be the `backend` subdirectory: the repo root
  # has no app.yaml, and pointing at it fails with
  # "No command to run and no Python file found".
  git)   WS_PATH="${WORKSPACE_PATH:-/Workspace/Users/$USER_NAME/$APP_NAME-git/backend}" ;;
  *)     echo "SOURCE_MODE must be 'local' or 'git' (got '$SOURCE_MODE')"; exit 1 ;;
esac
echo "user=$USER_NAME  app=$APP_NAME  mode=$SOURCE_MODE  source=$WS_PATH"

if [[ "$SOURCE_MODE" == "local" ]]; then
  step "Build dashboard into backend/static"
  if [[ "${SKIP_BUILD:-0}" == "1" ]]; then
    echo "SKIP_BUILD=1 — reusing existing bundle"
  else
    npm --prefix "$REPO_ROOT/frontend" run build
    rm -rf "$SOURCE_DIR/static"
    cp -r "$REPO_ROOT/frontend/dist" "$SOURCE_DIR/static"
  fi
  [[ -f "$SOURCE_DIR/static/index.html" ]] || { echo "backend/static/index.html missing"; exit 1; }
  [[ -f "$SOURCE_DIR/app.yaml" ]] || { echo "backend/app.yaml missing"; exit 1; }

  # Never ship: the venv, caches, tests, local SQLite/WAV artifacts, or any .env.
  # `databricks sync` honours .gitignore, so `static/` must stay un-ignored;
  # --include makes that explicit rather than implicit.
  SYNC_ARGS=(
    --include 'static/**'
    --exclude '.venv/**'
    --exclude '**/__pycache__/**'
    --exclude '.pytest_cache/**'
    --exclude 'tests/**'
    --exclude 'data/*.db'
    --exclude 'data/audio/**'
    --exclude '.env'
    --exclude 'requirements-dev.txt'
  )

  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    step "Dry-run sync"
    databricks sync "$SOURCE_DIR" "$WS_PATH" -p "$PROFILE" --full --dry-run "${SYNC_ARGS[@]}"
    echo "DRY_RUN=1 — stopping before deploy"
    exit 0
  fi

  step "Sync source to workspace"
  databricks sync "$SOURCE_DIR" "$WS_PATH" -p "$PROFILE" --full "${SYNC_ARGS[@]}"
else
  step "Git mode — deploying the Apps git-integration clone"
  # CAUTION: this does NOT pull. `apps deploy --source-code-path <clone>` deploys
  # whatever is currently in that path, and the clone is only refreshed by a
  # git-triggered deploy (UI Redeploy, or auto-deploy on push). If the clone is
  # behind origin, this silently ships stale code — a stale `static/` bundle in
  # particular gives you an old UI against a new API.
  # Prefer scripts/release.sh, which pushes and then deploys the (identical) local
  # tree. Use this mode only right after a UI Redeploy or with auto-deploy armed.
  # Warn loudly when the local tree isn't what will be deployed: git mode deploys
  # the remote commit, so uncommitted work (a rebuilt bundle especially) is invisible.
  if ! git -C "$REPO_ROOT" diff --quiet HEAD -- backend || \
     [[ -n "$(git -C "$REPO_ROOT" ls-files -o --exclude-standard -- backend/static)" ]]; then
    echo "WARNING: backend/ has uncommitted changes — they will NOT be deployed."
    echo "         Run scripts/release.sh to build, commit and push first."
  fi
  echo "local HEAD : $(git -C "$REPO_ROOT" rev-parse --short HEAD) on $(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "DRY_RUN=1 — would deploy $WS_PATH; stopping"
    exit 0
  fi
  databricks workspace get-status "$WS_PATH" -p "$PROFILE" -o json >/dev/null \
    || { echo "git clone path not found: $WS_PATH
Configure Git on the app first (App -> Edit -> Configure Git, source path 'backend')."; exit 1; }
fi

step "Ensure app exists"
databricks apps get "$APP_NAME" -p "$PROFILE" -o json >/dev/null 2>&1 \
  || databricks apps create "$APP_NAME" -p "$PROFILE" \
       --description "Audience Zero — synthetic test audience for serialized audio"

# The Secret resource is attachable via the API, so no UI step is required. This
# must land BEFORE the deploy: env vars are injected at deploy time, so attaching
# afterwards leaves the running process without OPENAI_API_KEY until a redeploy.
step "Attach secret resource + grant the app READ on the scope"
RESOURCES_JSON="$(dirname "${BASH_SOURCE[0]}")/app-resources.json"
if [[ -f "$RESOURCES_JSON" ]]; then
  databricks apps update "$APP_NAME" -p "$PROFILE" --json "@$RESOURCES_JSON" >/dev/null
  SP_ID="$(databricks apps get "$APP_NAME" -p "$PROFILE" -o json \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("service_principal_client_id") or "")')"
  if [[ -n "$SP_ID" ]]; then
    databricks secrets put-acl audience-zero "$SP_ID" READ -p "$PROFILE" 2>/dev/null || true
    echo "granted READ on scope audience-zero to app service principal $SP_ID"
  fi
else
  echo "no $RESOURCES_JSON — skipping (app will run in mock mode)"
fi

step "Deploy"
databricks apps deploy "$APP_NAME" -p "$PROFILE" --source-code-path "$WS_PATH" --auto-approve

step "Result"
databricks apps get "$APP_NAME" -p "$PROFILE" -o json | python3 -c '
import json, sys
a = json.load(sys.stdin)
url = a.get("url", "")
print("status :", (a.get("compute_status") or {}).get("state", "?"))
print("app    :", (a.get("app_status") or {}).get("state", "?"))
print("url    :", url)
print()
print("Verification gates (open in a browser — the app URL is behind Databricks OAuth):")
for p in ("/", "/api/health", "/api/debug/env-check", "/api/debug/ffmpeg", "/api/debug/sse-counter"):
    print("  ", url.rstrip("/") + p)
'
echo
echo "Logs: databricks apps logs $APP_NAME -p $PROFILE"
