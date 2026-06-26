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



def test_move_tail_layout_only_passes_when_pages_dont_increase():
    previous_qa = {"pages": 4, "layout_issues": [{"code": "last_page_sparse", "page": 4}]}
    comments = ["remonter la dernière mission clé de la derniere page sur page 3"]
    new_qa = {"pages": 4, "layout_issues": []}

    passed, warnings = verify_layout_revision_improved(
        previous_qa_report=previous_qa,
        new_qa_report=new_qa,
        comments=comments,
    )

    assert passed is True
    assert warnings == []


def test_move_tail_layout_only_fails_when_pages_increase():
    previous_qa = {"pages": 4, "layout_issues": [{"code": "last_page_sparse", "page": 4}]}
    comments = ["remonter la dernière mission clé de la derniere page sur page 3"]
    new_qa = {"pages": 5, "layout_issues": []}

    passed, warnings = verify_layout_revision_improved(
        previous_qa_report=previous_qa,
        new_qa_report=new_qa,
        comments=comments,
    )

    assert passed is False
    codes = [warning.get("code") for warning in warnings]
    assert "revision_added_pages" in codes


def test_move_tail_layout_only_fails_when_new_sparse_pages_appear():
    previous_qa = {"pages": 4, "layout_issues": [{"code": "last_page_sparse", "page": 4}]}
    comments = ["remonter la dernière mission clé de la derniere page sur page 3"]
    new_qa = {"pages": 5, "layout_issues": [{"code": "page_too_sparse", "page": 4}]}

    passed, warnings = verify_layout_revision_improved(
        previous_qa_report=previous_qa,
        new_qa_report=new_qa,
        comments=comments,
    )

    assert passed is False
    codes = [warning.get("code") for warning in warnings]
    assert "page_too_sparse" in codes


def test_non_layout_comments_skip_verification():
    comments = ["ajouter l'expérience Thales"]
    new_qa = {"pages": 99, "layout_issues": []}

    passed, warnings = verify_layout_revision_improved(
        previous_qa_report=None,
        new_qa_report=new_qa,
        comments=comments,
    )

    assert passed is True
    assert warnings == []


def test_no_move_intent_skips_verification():
    previous_qa = {"pages": 4, "layout_issues": [{"code": "last_page_sparse", "page": 4}]}
    comments = ["aérer"]
    new_qa = {"pages": 5, "layout_issues": []}

    passed, warnings = verify_layout_revision_improved(
        previous_qa_report=previous_qa,
        new_qa_report=new_qa,
        comments=comments,
    )

    assert passed is True
    assert warnings == []
