#!/usr/bin/env bash
# Deploy Audience Zero as a single-process Databricks App (FastAPI + built React
# bundle). Idempotent: safe to re-run for every iteration.
#
#   ./scripts/deploy_databricks.sh
#
# Env overrides:
#   DATABRICKS_PROFILE   ~/.databrickscfg profile      (default: hackathon)
#   APP_NAME             Databricks app name           (default: audience-zero)
#   WORKSPACE_PATH       source-code path in workspace (default: /Workspace/Users/<me>/<APP_NAME>)
#   SKIP_BUILD=1         reuse the existing backend/static bundle
#   DRY_RUN=1            show what would sync, deploy nothing
set -euo pipefail

APP_NAME="${APP_NAME:-audience-zero}"
PROFILE="${DATABRICKS_PROFILE:-hackathon}"
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
WS_PATH="${WORKSPACE_PATH:-/Workspace/Users/$USER_NAME/$APP_NAME}"
echo "user=$USER_NAME  app=$APP_NAME  source=$WS_PATH"

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
