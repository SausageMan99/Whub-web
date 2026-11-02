#!/usr/bin/env python3
"""W hub CV Factory — health check with Telegram alerts.

The October 2026 outage (every request failing for 2+ weeks after a Hermes
update) went unnoticed because nothing watched the outcomes. This script
checks, and alerts on Telegram:

- worker_down:          the systemd worker service is not active
- consecutive_failures: the N most recent finished real requests all failed
- queue_stuck:          a request waits in `submitted` / `processing` too long
- smoke_failed:         (--smoke) the reference CV does not reach ready/draft_ready

The same problem is re-sent at most every --repeat-hours; a "rétabli" message
is sent once everything is healthy again. Messages carry short request ids and
the worker's public error messages only — never candidate data.

Usage:
  python3 scripts/cv_health_alert.py              # checks, alert if needed
  python3 scripts/cv_health_alert.py --smoke      # + end-to-end smoke CV
  python3 scripts/cv_health_alert.py --dry-run    # print instead of sending
  python3 scripts/cv_health_alert.py --test       # send a test message
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKER_ENV = REPO / ".env"
TELEGRAM_ENV = Path("/root/.hermes/.env")
STATE_FILE = Path("/root/.local/state/whub-cv-health.json")
SERVICE = "whub-cv-worker"
FAILED = {"failed", "qa_failed", "dead_letter"}
FINISHED = FAILED | {"ready", "draft_ready", "needs_human_review"}


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip("\"'"))
    return values


def fetch_recent_requests(env: dict[str, str], limit: int = 30) -> list[dict]:
    key = env["SUPABASE_SERVICE_ROLE_KEY"]
    query = urllib.parse.urlencode({
        "select": "id,status,last_error,updated_at,source_file_path",
        "order": "updated_at.desc",
        "limit": str(limit),
    })
    request = urllib.request.Request(
        f"{env['SUPABASE_URL']}/rest/v1/cv_requests?{query}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        rows = json.load(response)
    # Smoke runs upload under smoke/ and are not user traffic.
    return [row for row in rows if not str(row.get("source_file_path") or "").startswith("smoke/")]


def _age_minutes(row: dict, now: datetime) -> float:
    updated = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
    return (now - updated).total_seconds() / 60


def evaluate(rows: list[dict], *, now: datetime, failure_streak: int, submitted_minutes: int,
             processing_minutes: int, service_active: bool) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    if not service_active:
        problems.append(("worker_down", f"Le service {SERVICE} n'est pas actif sur le VPS."))

    finished = [row for row in rows if row.get("status") in FINISHED]
    streak = 0
    for row in finished:
        if row["status"] not in FAILED:
            break
        streak += 1
    if streak >= failure_streak:
        details = "\n".join(
            f"• {row['id'][:8]} {row['status']} — {(row.get('last_error') or '')[:90]}" for row in finished[:streak][:5]
        )
        problems.append(("consecutive_failures", f"{streak} demandes d'affilée en échec :\n{details}"))

    stuck = [
        row for row in rows
        if (row.get("status") == "submitted" and _age_minutes(row, now) > submitted_minutes)
        or (row.get("status") == "processing" and _age_minutes(row, now) > processing_minutes)
    ]
    if stuck:
        details = "\n".join(f"• {row['id'][:8]} {row['status']} depuis {_age_minutes(row, now):.0f} min" for row in stuck[:5])
        problems.append(("queue_stuck", f"{len(stuck)} demande(s) bloquée(s) dans la file :\n{details}"))
    return problems


def run_smoke() -> tuple[str, str] | None:
    try:
        result = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "e2e_smoke.py"), "--case", "sanitize"],
            capture_output=True, text=True, timeout=900, cwd=REPO,
        )
    except subprocess.TimeoutExpired:
        return ("smoke_failed", "Le CV de test n'a pas abouti en 15 min.")
    status = None
    for line in result.stdout.splitlines():
        if line.startswith("[JSON] "):
            status = json.loads(line[len("[JSON] "):]).get("status")
    if status in {"ready", "draft_ready"}:
        return None
    return ("smoke_failed", f"Le CV de test quotidien finit en `{status or 'inconnu'}` (attendu ready/draft_ready).")


def send_telegram(text: str, *, dry_run: bool) -> None:
    if dry_run:
        print(text)
        return
    env = load_env(TELEGRAM_ENV)
    body = urllib.parse.urlencode({"chat_id": env["TELEGRAM_HOME_CHANNEL"], "text": text}).encode()
    request = urllib.request.Request(f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendMessage", data=body)
    with urllib.request.urlopen(request, timeout=30) as response:
        if json.load(response).get("ok") is not True:
            raise RuntimeError("Telegram sendMessage refused")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


def main() -> int:
    parser = argparse.ArgumentParser(description="CV Factory health alerts")
    parser.add_argument("--smoke", action="store_true", help="also run the end-to-end smoke CV")
    parser.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
    parser.add_argument("--test", action="store_true", help="send a test message and exit")
    parser.add_argument("--failure-streak", type=int, default=3)
    parser.add_argument("--submitted-minutes", type=int, default=20)
    parser.add_argument("--processing-minutes", type=int, default=45)
    parser.add_argument("--repeat-hours", type=float, default=6)
    args = parser.parse_args()

    if args.test:
        send_telegram("✅ CV Factory — test du canal d'alerte : les alertes de santé du worker arriveront ici.", dry_run=args.dry_run)
        return 0

    now = datetime.now(timezone.utc)
    service_active = subprocess.run(["systemctl", "is-active", "--quiet", SERVICE]).returncode == 0
    try:
        rows = fetch_recent_requests(load_env(WORKER_ENV))
        problems = evaluate(rows, now=now, failure_streak=args.failure_streak, submitted_minutes=args.submitted_minutes,
                            processing_minutes=args.processing_minutes, service_active=service_active)
    except Exception as exc:  # noqa: BLE001 - an unreachable database is itself an alert
        problems = [("supabase_unreachable", f"Lecture Supabase impossible ({type(exc).__name__}).")]
    if args.smoke:
        smoke_problem = run_smoke()
        if smoke_problem:
            problems.append(smoke_problem)

    state = load_state()
    signature = ",".join(sorted(code for code, _ in problems))
    last_sent = datetime.fromisoformat(state["last_sent_at"]) if state.get("last_sent_at") else None
    if problems:
        repeat_due = last_sent is None or now - last_sent >= timedelta(hours=args.repeat_hours)
        if signature != state.get("signature") or repeat_due:
            text = "🚨 CV Factory — problème détecté\n\n" + "\n\n".join(message for _, message in problems)
            send_telegram(text, dry_run=args.dry_run)
            state = {"signature": signature, "last_sent_at": now.isoformat()}
    elif state.get("signature"):
        send_telegram("✅ CV Factory — rétabli : plus de problème détecté.", dry_run=args.dry_run)
        state = {}
    if not args.dry_run:
        save_state(state)
    print(json.dumps({"problems": [code for code, _ in problems], "service_active": service_active}))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
