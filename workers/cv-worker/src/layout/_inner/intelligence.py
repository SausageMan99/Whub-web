from __future__ import annotations

from copy import deepcopy
from typing import Any

SPARSE_LAYOUT_CODES = {
    "page_too_sparse",
    "last_page_sparse",
    "page_underfilled_with_next_experience_fit",
}

DENSE_LAYOUT_CODES = {
    "page_too_dense",
    "experience_orphan_heading",
    "experience_section_orphan_heading",
    "bad_page_break",
}


def _layout_issue_codes(qa_report: dict[str, Any] | None) -> set[str]:
    if not isinstance(qa_report, dict):
        return set()
    codes: set[str] = set()
    for issue in qa_report.get("layout_issues") or []:
        if isinstance(issue, dict) and issue.get("code"):
            codes.add(str(issue["code"]))
    return codes


def _max_numeric(existing: Any, minimum: float | int) -> float | int:
    if isinstance(existing, (int, float)) and not isinstance(existing, bool):
        return max(existing, minimum)
    return minimum


def _min_numeric(existing: Any, maximum: float | int) -> float | int:
    if isinstance(existing, (int, float)) and not isinstance(existing, bool):
        return min(existing, maximum)
    return maximum


def build_layout_retry_options(base_options: dict[str, Any] | None, qa_report: dict[str, Any] | None) -> dict[str, Any]:
    """Build safe renderer-only layout retry options from QA layout codes.

    The retry is intentionally limited to placement / density hints. It never
    receives or mutates structured CV content. Sparse pages win over dense-page
    heuristics because forcing each experience to a new page can recreate sparse
    continuation pages.
    """
    options: dict[str, Any] = deepcopy(base_options) if isinstance(base_options, dict) else {}
    codes = _layout_issue_codes(qa_report)
    has_sparse_issue = bool(codes & SPARSE_LAYOUT_CODES)
    has_dense_issue = bool(codes & DENSE_LAYOUT_CODES)

    if not has_sparse_issue and not has_dense_issue:
        return options

    options["anti_crowding"] = True

    if has_sparse_issue:
        # Regroup naturally: sparse/underfilled pages indicate the retry must not
        # isolate every experience or preserve stale forced break hints.
        options["force_experiences_new_page"] = False
        options["force_page_break_before_experience_indexes"] = []
        options["allow_grouping"] = True
        options["density_profile"] = options.get("density_profile") or "balanced"
        options["page_dense_char_threshold"] = _max_numeric(options.get("page_dense_char_threshold"), 2850)
        options["max_used_ratio"] = _max_numeric(options.get("max_used_ratio"), 0.86)
        options.setdefault("readability_reserve", 130)
        return options

    # Dense/orphan/bad-break retry: keep anti-crowding and make the renderer more
    # conservative, while preserving existing break hints from the packing pass.
    # Only dense-only reports may force every experience onto a new page.
    options["force_experiences_new_page"] = True
    options.setdefault("force_page_break_before_experience_indexes", [])
    options["page_dense_char_threshold"] = _min_numeric(options.get("page_dense_char_threshold"), 2600)
    options["max_used_ratio"] = _min_numeric(options.get("max_used_ratio"), 0.80)
    options.setdefault("readability_reserve", 170)
    return options


__all__ = [
    "SPARSE_LAYOUT_CODES",
    "DENSE_LAYOUT_CODES",
    "_layout_issue_codes",
    "_max_numeric",
    "_min_numeric",
    "build_layout_retry_options",
]