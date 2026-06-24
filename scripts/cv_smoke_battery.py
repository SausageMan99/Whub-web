#!/usr/bin/env python3
"""W hub CV Factory — battery smoke runner.

Iterates over the test bank, runs `e2e_smoke.py --case <case>` for each one,
writes machine-readable JSONL results and a human log.

Usage examples:
  python3 scripts/cv_smoke_battery.py
  python3 scripts/cv_smoke_battery.py --case oussama,zahia,dense
  python3 scripts/cv_smoke_battery.py --retry 1
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

CASES = [
    "oussama",
    "zahia",
    "thorez",
    "dense",
    "sanitize",
    "hodard",
    "rayan",
    "amina",
]
SMOKE = Path(__file__).with_name("e2e_smoke.py")
RESULTS = Path(__file__).with_name("cv_smoke_results.jsonl")
LOG = Path("/tmp/cv_smoke_battery.log")


def log(msg: str) -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def reset() -> None:
    for path in (RESULTS, LOG):
        if path.exists():
            path.unlink()


def run_case(case: str) -> dict:
    log(f"\n=== {case} ===")
    t0 = time.time()
    res = subprocess.run(
        [sys.executable, str(SMOKE), "--case", case],
        capture_output=True,
        text=True,
    )
    duration = round(time.time() - t0, 2)
    log("\n".join(res.stdout.splitlines()))
    if res.returncode != 0:
        err = "\n".join(res.stderr.splitlines())
        log(f"[ERR] {case} rc={res.returncode}")
        if err:
            log(err)
        return {"case": case, "status": "error", "duration_seconds": duration, "returncode": res.returncode}
    payload = None
    for line in res.stdout.splitlines():
        if line.startswith("[JSON]"):
            payload = json.loads(line.split("[JSON] ", 1)[1])
            break
    if payload is None:
        log(f"[ERR] {case}: missing JSON payload")
        return {"case": case, "status": "error", "duration_seconds": duration, "returncode": 1}
    payload["case"] = case
    payload["duration_seconds"] = duration
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="CV Factory battery smoke")
    parser.add_argument("--case", default=None, help="comma-separated cases")
    parser.add_argument("--retry", type=int, default=0, help="retry failed cases once")
    parser.add_argument("--reset", action="store_true", help="wipe results/log before run")
    parser.add_argument("--append", action="store_true", help="append to existing results/log instead of starting clean")
    args = parser.parse_args()
    if args.reset or not args.append:
        reset()

    cases = [c.strip() for c in (args.case or ",".join(CASES)).split(",") if c.strip()]
    cases = [c for c in cases if c in CASES]
    if not cases:
        log("No valid cases selected.")
        return 1

    results: list[dict] = []
    failed: list[str] = []
    for index, case in enumerate(cases, 1):
        log(f"[{index}/{len(cases)}] {case}")
        payload = run_case(case)
        results.append(payload)
        if payload.get("status") not in {"ready", "draft_ready"} or not payload.get("quality_event_seen"):
            failed.append(case)

    failed = list(dict.fromkeys(failed))
    for attempt in range(1, args.retry + 1):
        if not failed:
            break
        log(f"\n=== RETRY {attempt}/{args.retry} ===")
        retry_list = failed[:]
        failed = []
        for case in retry_list:
            payload = run_case(case)
            payload.setdefault("retry_of", case)
            results.append(payload)
            if payload.get("status") not in {"ready", "draft_ready"} or not payload.get("quality_event_seen"):
                failed.append(case)

    passed = sum(1 for r in results if r.get("quality_event_seen") and r.get("status") in {"ready", "draft_ready"})
    log(f"\n=== DONE passed={passed}/{len(results)} failed={failed} ===")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
