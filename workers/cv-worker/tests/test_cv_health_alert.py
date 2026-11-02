"""Tests for the CV Factory health alert evaluator."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from cv_health_alert import evaluate  # noqa: E402

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def _row(index: int, status: str, minutes_ago: float = 60, error: str = "") -> dict:
    return {
        "id": f"{index:08d}-0000-0000-0000-000000000000",
        "status": status,
        "last_error": error,
        "updated_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
    }


def _evaluate(rows, service_active=True):
    return evaluate(rows, now=NOW, failure_streak=3, submitted_minutes=20, processing_minutes=45,
                    service_active=service_active)


def test_october_outage_pattern_raises_consecutive_failures():
    # Every request failing with the same public message, as from 2026-10-16.
    rows = [_row(i, "failed", 60 + i, "Le modèle de structuration a échoué (sortie en erreur).") for i in range(10)]

    problems = dict(_evaluate(rows))

    assert "consecutive_failures" in problems
    assert "10 demandes" in problems["consecutive_failures"]
    assert "Le modèle de structuration a échoué" in problems["consecutive_failures"]


def test_a_recent_success_breaks_the_failure_streak():
    rows = [_row(0, "draft_ready"), _row(1, "failed"), _row(2, "failed"), _row(3, "failed")]

    assert _evaluate(rows) == []


def test_in_flight_rows_do_not_break_or_extend_the_streak():
    rows = [_row(0, "processing", 2), _row(1, "failed"), _row(2, "qa_failed"), _row(3, "dead_letter")]

    assert [code for code, _ in _evaluate(rows)] == ["consecutive_failures"]


def test_old_submitted_request_is_reported_as_stuck():
    rows = [_row(0, "submitted", 35), _row(1, "ready")]

    problems = dict(_evaluate(rows))

    assert "queue_stuck" in problems
    assert "00000000" in problems["queue_stuck"]


def test_fresh_submitted_request_is_not_stuck():
    assert _evaluate([_row(0, "submitted", 3), _row(1, "ready")]) == []


def test_inactive_service_is_reported():
    assert [code for code, _ in _evaluate([_row(0, "ready")], service_active=False)] == ["worker_down"]
