from __future__ import annotations

import re
from typing import Any

from ._inner.intelligence import build_layout_retry_options, _layout_issue_codes


MOVE_TAIL_KEYWORDS = re.compile(
    r"\b(remont(?:e|er)|montez?|descend(?:s|re)?|d[eé]plac(?:e|er)|mets?|mettre|rapproch(?:e|er))\b",
    re.I,
)
PAGE_REF_RE = re.compile(r"\bpage\s*\d+\b|\bderni[eè]re\s+page\b|\bpremi[eè]re\s+page\b", re.I)


def mentions_move_from_last_page(comments: list[str]) -> bool:
    text = " ".join(comments or [])
    if not text.strip():
        return False
    has_move = bool(MOVE_TAIL_KEYWORDS.search(text))
    has_page_ref = bool(PAGE_REF_RE.search(text))
    # A "move" instruction targeting a page reference or last/first page
    return has_move and has_page_ref


def build_layout_revision_options(
    *,
    base_options: dict[str, Any],
    previous_qa_report: dict[str, Any] | None,
    comments: list[str],
) -> dict[str, Any]:
    """Build renderer-only layout hints targeted at user pagination comments.

    Falls back to build_layout_retry_options() when no layout-only intent.
    Sets revision_intent='move_tail_from_sparse_last_page' only when comments
    request moving content AND the previous QA flagged a sparse last page.
    Never mutates structured content; only renderer hints.
    """
    options = build_layout_retry_options(base_options, previous_qa_report)
    codes = _layout_issue_codes(previous_qa_report)
    if not mentions_move_from_last_page(comments):
        return options
    has_sparse = bool(codes & {"page_too_sparse", "last_page_sparse", "page_underfilled_with_next_experience_fit"})
    if not has_sparse:
        return options
    options["force_experiences_new_page"] = False
    options["force_page_break_before_experience_indexes"] = []
    options["allow_grouping"] = True
    options["anti_crowding"] = True
    options["density_profile"] = "compact_balanced"
    options["page_dense_char_threshold"] = max(int(options.get("page_dense_char_threshold", 3200)), 3200)
    options["max_used_ratio"] = max(float(options.get("max_used_ratio", 0.90)), 0.90)
    options["readability_reserve"] = min(int(options.get("readability_reserve", 130)), 90)
    options["revision_intent"] = "move_tail_from_sparse_last_page"
    return options


__all__ = [
    "build_layout_revision_options",
    "mentions_move_from_last_page",
]
