from __future__ import annotations

from .content_blocks import ContentBlock, SourceDocument
from .layout_plan import LayoutPlan, validate_layout_plan

_SIDEBAR_TYPES = {"skills", "education", "languages", "certifications"}


def build_deterministic_layout_plan(document: SourceDocument) -> LayoutPlan:
    sidebar: list[str] = []
    main: list[str] = []
    for block in document.ordered_blocks():
        if not block.required:
            continue
        if block.type in _SIDEBAR_TYPES and block.estimated_lines <= 14:
            sidebar.append(block.id)
        else:
            main.append(block.id)
    zones = []
    if main:
        zones.append({"zone": "main", "block_ids": main})
    if sidebar:
        zones.append({"zone": "right_sidebar", "block_ids": sidebar})
    plan = LayoutPlan(
        strategy="deterministic_content_preserving",
        pages=[{"page": 1, "zones": zones}],
        density="normal",
        spacing="normal",
        avoid_splitting_blocks=[block.id for block in document.blocks if block.type == "experience"],
    )
    validate_layout_plan(plan, document)
    return plan
