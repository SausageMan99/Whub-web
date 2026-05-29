from __future__ import annotations

from copy import deepcopy


_LAYOUT_RETRY_ALLOWED_INTERNAL_KEYS = {"_layout"}


def _without_layout_retry_internal_keys(data: dict) -> dict:
    cleaned = deepcopy(data)
    for key in _LAYOUT_RETRY_ALLOWED_INTERNAL_KEYS:
        cleaned.pop(key, None)
    return cleaned


def assert_layout_retry_preserves_content(original: dict, retry_payload: dict) -> None:
    """Allow retry metadata only; dates/sections/bullets/skills/experiences must stay exact."""
    if _without_layout_retry_internal_keys(original) != _without_layout_retry_internal_keys(retry_payload):
        raise AssertionError("layout retry mutated structured content")


def is_safe_layout_retry_report(report: dict) -> bool:
    """Retry only pure density failures; never mask contact/security/overflow/asset failures."""
    layout_issues = report.get("layout_issues") or []
    codes = {issue.get("code") for issue in layout_issues if isinstance(issue, dict)}
    return (
        bool(codes.intersection({"page_too_dense", "last_page_sparse", "page_too_sparse", "bad_page_break", "experience_orphan_heading", "experience_section_orphan_heading", "page_underfilled_with_next_experience_fit"}))
        and not report.get("contact_hits")
        and not report.get("bad_glyphs")
        and not report.get("content_integrity_issues")
        and not report.get("text_overflow_hits")
        and bool(report.get("has_logo"))
        and bool(report.get("has_watermark"))
    )
