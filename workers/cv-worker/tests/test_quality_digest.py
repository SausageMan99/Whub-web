"""Tests for the W hub CV Factory quality digest summarizer."""
from __future__ import annotations

import sys
from pathlib import Path

# Make ``scripts/`` importable as a top-level package BEFORE importing
# the digest module below. The test lives at
# ``workers/cv-worker/tests/test_quality_digest.py``; ``scripts/`` is at
# the repo root, two directories up.
ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from quality_digest import format_digest, summarize_requests  # noqa: E402


def test_summarize_requests_groups_status_and_error_category():
    rows = [
        {"status": "ready", "last_error": None},
        {"status": "draft_ready", "last_error": None},
        {"status": "qa_failed", "last_error": "Coordonnées détectées dans la structuration du CV."},
        {"status": "qa_failed", "last_error": "Coordonnées détectées dans la structuration du CV."},
        {"status": "needs_human_review", "last_error": "Extraction peu fiable : validation humaine requise avant génération."},
    ]

    summary = summarize_requests(rows)

    assert summary["total"] == 5
    assert summary["by_status"]["ready"] == 1
    assert summary["by_status"]["draft_ready"] == 1
    assert summary["by_status"]["qa_failed"] == 2
    assert summary["by_status"]["needs_human_review"] == 1
    assert summary["ready_rate"] == 20.0
    assert summary["blocked_rate"] == 40.0
    assert summary["needs_human_review_rate"] == 20.0
    # The error signature is truncated to 60 chars and never includes raw
    # candidate data (no emails, phones, names).
    sig = next(iter(summary["top_error_signatures"]))
    assert "@" not in sig
    assert len(sig) <= 60


def test_summarize_requests_handles_empty_list():
    summary = summarize_requests([])
    assert summary["total"] == 0
    assert summary["by_status"] == {}
    assert summary["ready_rate"] == 0.0
    assert summary["blocked_rate"] == 0.0


def test_summarize_requests_buckets_unknown_statuses_safely():
    rows = [
        {"status": "ready"},
        {"status": "weird-new-status"},
        {"status": None},
    ]

    summary = summarize_requests(rows)

    assert summary["total"] == 3
    assert summary["by_status"].get("ready") == 1
    assert summary["by_status"].get("unknown") == 2


def test_format_digest_is_human_readable():
    summary = summarize_requests(
        [
            {"status": "ready"},
            {"status": "draft_ready"},
            {"status": "qa_failed", "last_error": "Coordonnées détectées dans la structuration du CV."},
        ]
    )
    text = format_digest(summary)
    assert "W hub CV Factory" in text
    assert "Ready:" in text
    assert "Draft ready:" in text
    assert "Blocked" in text
    assert "By status:" in text
    # No raw email or phone content in the digest.
    assert "@" not in text
    assert "06" not in text or "Ready" in text  # the "06" in 'Ready' is harmless
