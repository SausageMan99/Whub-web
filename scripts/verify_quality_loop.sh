#!/usr/bin/env bash
# W hub CV Factory — local quality loop verification gate.
#
# Runs the targeted tests for the auto-evaluation loop in both the worker
# (Python) and the web (TypeScript) projects, plus the digest and eval runner
# smoke tests. This is the local pre-push gate. It does NOT push, deploy,
# restart the worker, or migrate the database.
#
# Usage: ./scripts/verify_quality_loop.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Worker quality loop tests ==="
cd "$ROOT/workers/cv-worker"
uv run pytest \
  tests/test_quality_report.py \
  tests/test_main_quality_report.py \
  tests/test_main_needs_human_review.py \
  tests/test_draft_ready.py \
  tests/test_qa_layout_policy.py \
  tests/test_main_layout_retry.py \
  tests/test_main_error_taxonomy.py \
  tests/test_eval_runner.py \
  tests/test_quality_digest.py \
  -q

echo
echo "=== Web quality loop tests ==="
cd "$ROOT/apps/web"
npx tsx --test --experimental-test-module-mocks \
  tests/cv-ui.test.ts \
  tests/request-detail-ui.test.ts \
  tests/request-detail-page.test.ts \
  tests/request-detail-quality.test.ts \
  tests/revision-request.test.ts \
  --test-reporter=spec

echo
echo "=== Eval case schema validation ==="
cd "$ROOT"
python3 - <<'PY'
import json
import sys
from pathlib import Path

cases = list(Path("workers/cv-worker/eval/cases").glob("*.json"))
if not cases:
    print("No eval cases found.")
    sys.exit(1)
for path in cases:
    json.loads(path.read_text())
    print(f"  OK: {path}")
PY

echo
echo "=== Quality loop verification: PASS ==="
