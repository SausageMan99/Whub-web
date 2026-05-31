#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER_DIR="$ROOT_DIR/workers/cv-worker"

run() {
  echo
  echo "==> $*"
  "$@"
}

run_bash() {
  echo
  echo "==> $*"
  bash -lc "$*"
}

cd "$ROOT_DIR"
run npm run lint
run npm test
run npm run build

cd "$WORKER_DIR"
export WHUB_RENDERER_PATH="$WORKER_DIR/renderer/whub_cv_renderer.py"
export WHUB_ASSETS_DIR="$WORKER_DIR/assets/whub"
export WHUB_FONTS_DIR="$WORKER_DIR/assets/fonts/poppins"
run_bash "PYTHONPATH=. pytest -q"
run_bash "python -m compileall -q src renderer scripts"
run_bash "python scripts/verify_whub_assets.py"

cd "$ROOT_DIR"
run git diff --check

echo
echo "verify_all: GO"
