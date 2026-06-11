"""W hub CV Factory — quality digest summarizer.

The digest is a pure, dependency-free helper that consumes a list of CV
request rows and produces a small status/health summary. It does NOT call
Supabase, the model, or any external service: the data fetch is left to
the caller so the same summarizer can be used by a cron, by a Telegram
report, or by a debug script.

Usage from a cron job:

    from supabase import create_client
    from scripts.quality_digest import summarize_requests, format_digest

    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    rows = client.table("cv_requests").select("status,last_error,created_at").execute().data
    print(format_digest(summarize_requests(rows)))
"""
from __future__ import annotations

from collections import Counter
from typing import Any


_RECOGNIZED_STATUSES = {
    "submitted",
    "processing",
    "qa_failed",
    "draft_ready",
    "ready",
    "revision_requested",
    "failed",
    "dead_letter",
    "cancelled",
    "archived",
    "needs_human_review",
}


def summarize_requests(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregated quality metrics from a list of cv_requests rows.

    Each row is expected to expose at least ``status`` and ``last_error``
    fields. The function never raises on missing or unknown statuses; it
    buckets them under ``"unknown"`` instead so a bad row never breaks the
    digest.
    """
    total = len(rows)
    by_status: Counter[str] = Counter()
    error_counter: Counter[str] = Counter()
    for row in rows:
        status = str(row.get("status") or "unknown")
        if status not in _RECOGNIZED_STATUSES:
            status = "unknown"
        by_status[status] += 1
        if status in {"qa_failed", "failed", "dead_letter", "needs_human_review"}:
            err = str(row.get("last_error") or "").strip()
            if err:
                # We only keep the first 60 chars and never the full
                # message to avoid leaking candidate data in the digest.
                error_counter[err[:60]] += 1

    def pct(n: int) -> float:
        return round((n / total) * 100, 1) if total else 0.0

    blocked = by_status.get("qa_failed", 0) + by_status.get("failed", 0) + by_status.get("dead_letter", 0)
    review = by_status.get("needs_human_review", 0)
    return {
        "total": total,
        "by_status": dict(sorted(by_status.items())),
        "ready_rate": pct(by_status.get("ready", 0)),
        "draft_ready_rate": pct(by_status.get("draft_ready", 0)),
        "blocked_rate": pct(blocked),
        "needs_human_review_rate": pct(review),
        "top_error_signatures": dict(error_counter.most_common(5)),
    }


def format_digest(summary: dict[str, Any]) -> str:
    """Format a digest summary as a plain-text report suitable for Telegram or logs."""
    lines = [
        "W hub CV Factory — quality digest",
        f"Total: {summary['total']}",
        f"Ready: {summary['ready_rate']}%",
        f"Draft ready: {summary['draft_ready_rate']}%",
        f"Blocked (qa_failed / failed / dead_letter): {summary['blocked_rate']}%",
        f"Needs human review: {summary['needs_human_review_rate']}%",
        f"By status: {summary['by_status']}",
    ]
    top = summary.get("top_error_signatures") or {}
    if top:
        lines.append("Top error signatures (truncated, redacted):")
        for sig, count in top.items():
            lines.append(f"  - {count}× {sig}")
    return "\n".join(lines)
