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
    page_capacity_units: int = 21,
    min_fill_units: int = 10,
) -> list[int]:
    """Pack sequential experiences into pages and return break-before indexes.

    The algorithm preserves order and only decides before which experience a new
    page should start. It favours adding the next experience when it fits, avoiding
    sparse pages, while refusing to split an experience opener/body by content
    mutation. Names/clients are intentionally ignored.
    """
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
    experiences = [exp for exp in (data.get("experiences") or []) if isinstance(exp, dict)]
    units = [estimate_experience_units(exp) for exp in experiences]
    total_units = sum(units)
    max_units = max(units, default=0)
    # Short / medium CVs like THOREZ should be grouped naturally. Forcing all
    # experiences onto continuation pages and adding deterministic breaks can turn
    # two pages of source material into four sparse pages. Reserve forced packing
    # for genuinely heavy experience sets.
    is_short_groupable_cv = bool(experiences) and len(experiences) <= 6 and total_units <= 45 and max_units <= 10
    auto_force_experiences = force_experiences_new_page is None
    if auto_force_experiences:
        force_experiences_new_page = not is_short_groupable_cv
    breaks = [] if (auto_force_experiences and is_short_groupable_cv) else compute_experience_page_breaks(experiences)
    return {
        "anti_crowding": True,
        "force_experiences_new_page": force_experiences_new_page,
        "force_page_break_before_experience_indexes": breaks,
        "allow_grouping": True,
        "density_profile": "balanced",
        "page_dense_char_threshold": 2850,
        "max_used_ratio": 0.86,
        "readability_reserve": 130,
    }


def assert_packing_preserves_experience_content(original: dict[str, Any], packed_payload: dict[str, Any]) -> None:
    cleaned = deepcopy(packed_payload)
    cleaned.pop("_layout", None)
    if cleaned != original:
        raise AssertionError("layout packing mutated structured content")
