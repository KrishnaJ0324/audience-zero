#!/usr/bin/env bash
# One command per release, for the git-backed deploy flow:
#   test -> build dashboard -> stage backend/static -> commit -> push -> deploy
#
#   ./scripts/release.sh "fix beat-7 evidence spans"
#
# Why the bundle is committed: Databricks Apps installs requirements.txt but never
# runs npm, so the built React bundle has to arrive with the code. A git deploy
# ships whatever `backend/static/` is at that commit — rebuilding locally without
# committing leaves the deployed UI a version behind the API.
#
# Env overrides:
#   DATABRICKS_PROFILE  ~/.databrickscfg profile   (default: hackathon)
#   BRANCH              branch to push             (default: current)
#   REMOTE              git remote                 (default: origin)
#   SKIP_TESTS=1        skip the backend test run
#   NO_DEPLOY=1         commit + push only, don't deploy
set -euo pipefail

MSG="${1:-}"
[[ -n "$MSG" ]] || { echo "usage: ./scripts/release.sh \"commit message\""; exit 1; }

PROFILE="${DATABRICKS_PROFILE:-hackathon}"
REMOTE="${REMOTE:-origin}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${BRANCH:-$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)}"
cd "$REPO_ROOT"

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Tests"
if [[ "${SKIP_TESTS:-0}" == "1" ]]; then
  echo "SKIP_TESTS=1 — skipped"
else
  # Mock provider is mandatory: .env carries a real key and AZ_PROVIDER=auto, so an
  # unguarded run would resolve to OpenAI and bill real calls.
  ( cd backend && AZ_PROVIDER=mock AZ_REVEAL_DELAY_S=0 .venv/bin/python -m pytest -q )
fi

step "Build dashboard"
npm --prefix frontend run build
rm -rf backend/static
cp -r frontend/dist backend/static
[[ -f backend/static/index.html ]] || { echo "build produced no index.html"; exit 1; }

step "Guard: no secrets in what we're about to commit"
if git ls-files -co --exclude-standard -z \
   | xargs -0 grep -lE 'sk-[A-Za-z0-9_-]{20,}|dapi[0-9a-f]{16,}' 2>/dev/null | grep -q .; then
  echo "ABORT: key-shaped string found in a committable file:"
  git ls-files -co --exclude-standard -z \
    | xargs -0 grep -lE 'sk-[A-Za-z0-9_-]{20,}|dapi[0-9a-f]{16,}' 2>/dev/null
  exit 1
fi
git check-ignore -q .env || { echo "ABORT: .env is not gitignored"; exit 1; }
echo "clean"

step "Commit + push"
git add -A backend/static backend/app backend/app.yaml backend/requirements.txt \
            backend/requirements-dev.txt scripts README.md DEPLOY_RUNBOOK.md 2>/dev/null || true
git add -A
if git diff --cached --quiet; then
  echo "nothing staged — reusing HEAD $(git rev-parse --short HEAD)"
else
  git commit -m "$MSG"
fi
git push "$REMOTE" "$BRANCH"
echo "pushed $(git rev-parse --short HEAD) to $REMOTE/$BRANCH"

if [[ "${NO_DEPLOY:-0}" == "1" ]]; then
  echo "NO_DEPLOY=1 — stopping before deploy"
  exit 0
fi

step "Deploy that commit from the app's Git clone"
SOURCE_MODE=git DATABRICKS_PROFILE="$PROFILE" ./scripts/deploy_databricks.sh
