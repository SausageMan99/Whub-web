from __future__ import annotations

import re
from typing import Any


MOVE_TAIL_KEYWORDS = re.compile(
    r"\b(remont(?:e|er)|montez?|descend(?:s|re)?|d[eé]plac(?:e|er)|mets?|mettre|rapproch(?:e|er))\b",
    re.I,
)
PAGE_REF_RE = re.compile(r"\bpage\s*\d+\b|\bderni[eè]re\s+page\b|\bpremi[eè]re\s+page\b", re.I)


def _mentions_move_from_last_page(comments: list[str]) -> bool:
    text = " ".join(comments or [])
    if not text.strip():
        return False
    return bool(MOVE_TAIL_KEYWORDS.search(text) and PAGE_REF_RE.search(text))


def verify_layout_revision_improved(
    *,
    previous_qa_report: dict[str, Any] | None,
    new_qa_report: dict[str, Any] | None,
    comments: list[str],
) -> tuple[bool, list[dict[str, Any]]]:
    """Verify a layout-only revision did not silently regress pagination.

    For move-tail layout_only intents, the new report must:
      - not add pages (same or fewer than previous)
      - not introduce new sparse pages
    Returns (passed, warnings). When passed=False, the caller should
    mark draft_ready (not ready) and surface warnings to the user.
    """
    warnings: list[dict[str, Any]] = []
    if not isinstance(new_qa_report, dict):
        return True, warnings
    if not _mentions_move_from_last_page(comments):
        return True, warnings
    prev_pages = int((previous_qa_report or {}).get("pages") or 0)
    new_pages = int(new_qa_report.get("pages") or 0)
    if new_pages > prev_pages:
        warnings.append({
            "code": "revision_added_pages",
            "message": f"La correction de pagination a ajouté des pages ({prev_pages} → {new_pages}).",
            "previous_pages": prev_pages,
            "new_pages": new_pages,
        })
    new_issues = new_qa_report.get("layout_issues") or []
    if isinstance(new_issues, list):
        for issue in new_issues:
            if isinstance(issue, dict) and issue.get("code") in {"page_too_sparse", "last_page_sparse"}:
                warnings.append(issue)
    return (not warnings), warnings


__all__ = ["verify_layout_revision_improved"]
