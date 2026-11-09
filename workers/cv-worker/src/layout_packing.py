from __future__ import annotations

from copy import deepcopy
from typing import Any


def _content_items(content: Any) -> list[str]:
    if isinstance(content, list):
        return [str(item).strip() for item in content if str(item).strip()]
    if isinstance(content, str) and content.strip():
        return [part.strip() for part in content.replace("\n", ";").split(";") if part.strip()]
    return []


def estimate_experience_units(exp: dict[str, Any]) -> int:
    """Small deterministic proxy for rendered height.

    This is deliberately based on structure/length, never on company names, so layout
    decisions cannot mutate or semantically rewrite the CV.
    """
    units = 2  # date + role opener
    for section in exp.get("sections") or []:
        if not isinstance(section, dict):
            continue
        if section.get("heading"):
            units += 1
        items = _content_items(section.get("content"))
        if not items and section.get("content"):
            units += 1
        for item in items:
            # One unit for a normal bullet, extra units for long wrapping bullets.
            units += max(1, min(3, (len(item) + 115) // 116))
    return max(3, units)


def compute_experience_page_breaks(
    experiences: list[dict[str, Any]],
    *,
    page_capacity_units: int = 58,
    min_fill_units: int | None = None,
) -> list[int]:
    """Pack sequential experiences into pages and return break-before indexes.

    The algorithm preserves order and only decides before which experience a new
    page should start. It favours adding the next experience when it fits, avoiding
    sparse pages, while refusing to split an experience opener/body by content
    mutation. Names/clients are intentionally ignored.
    """
    # A unit is about one rendered line: a full-width page holds ~70 lines,
    # 58 leaves room for headings and spacing (the former 21 cut pages at a
    # third of their height). Below ~half a page, the page is sparse.
    if min_fill_units is None:
        min_fill_units = page_capacity_units * 10 // 21
    breaks: list[int] = []
    used = 0
    for index, exp in enumerate(experiences):
        units = estimate_experience_units(exp)
        if index == 0:
            used = min(units, page_capacity_units)
            continue
        if used + units <= page_capacity_units:
            used += units
            continue
        # If the current page is very sparse, accept a slightly denser page rather
        # than wasting a page. Otherwise start a new page before this experience.
        if used < min_fill_units and used + units <= page_capacity_units + 3:
            used += units
            continue
        breaks.append(index)
        used = min(units, page_capacity_units)
    return breaks


def build_layout_packing_options(data: dict[str, Any], *, force_experiences_new_page: bool | None = None) -> dict[str, Any]:
    """Renderer placement hints for a structured CV.

    Since lot 1 of the PDF quality work (2026-11) the renderer decides page
    breaks on the height really left on the page (heading kept with its
    first lines, bullets split between lines, short tails rebalanced). The
    former hints (anti_crowding with a 2 850 character page budget, forced
    breaks every 21 "units" for heavy CVs) left most pages half empty, so the
    default packing forces nothing. Forced breaks remain available on an
    explicit request (force_experiences_new_page=True).
    """
    experiences = [exp for exp in (data.get("experiences") or []) if isinstance(exp, dict)]
    forced = bool(force_experiences_new_page)
    breaks = compute_experience_page_breaks(experiences) if forced else []
    return {
        "force_experiences_new_page": forced,
        "force_page_break_before_experience_indexes": breaks,
        "allow_grouping": True,
        "density_profile": "measured_height",
    }


def assert_packing_preserves_experience_content(original: dict[str, Any], packed_payload: dict[str, Any]) -> None:
    cleaned = deepcopy(packed_payload)
    cleaned.pop("_layout", None)
    if cleaned != original:
        raise AssertionError("layout packing mutated structured content")
