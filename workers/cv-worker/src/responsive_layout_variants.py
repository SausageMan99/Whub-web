from __future__ import annotations

from .content_blocks import SourceDocument
from .deterministic_layout_planner import build_deterministic_layout_plan
from .layout_plan import LayoutPlan, validate_layout_plan


def build_layout_variants(document: SourceDocument) -> list[LayoutPlan]:
    natural = build_deterministic_layout_plan(document)
    compact = LayoutPlan(
        strategy="compact_content_preserving",
        pages=natural.pages,
        density="compact",
        spacing="compact",
        avoid_splitting_blocks=natural.avoid_splitting_blocks,
    )
    experience_first_ids = [block.id for block in document.ordered_blocks() if block.required and block.type == "experience"]
    other_ids = [block.id for block in document.ordered_blocks() if block.required and block.type != "experience"]
    experience_first = LayoutPlan(
        strategy="experience_first_content_preserving",
        pages=[{"page": 1, "zones": [{"zone": "main", "block_ids": experience_first_ids + other_ids}]}],
        density="normal",
        spacing="normal",
        avoid_splitting_blocks=experience_first_ids,
    )
    variants = [natural, compact, experience_first]
    for variant in variants:
        validate_layout_plan(variant, document)
    return variants
