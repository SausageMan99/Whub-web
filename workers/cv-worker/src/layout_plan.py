from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .content_blocks import SourceDocument

Density = Literal["comfortable", "normal", "compact"]


class LayoutPlanError(ValueError):
    pass


@dataclass(frozen=True)
class LayoutPlan:
    strategy: str
    pages: list[dict[str, Any]]
    density: Density = "normal"
    spacing: Density = "normal"
    avoid_splitting_blocks: list[str] | None = None

    def used_block_ids(self) -> set[str]:
        ids: set[str] = set()
        for page in self.pages:
            for zone in page.get("zones", []):
                ids.update(str(block_id) for block_id in zone.get("block_ids", []))
        return ids


def validate_layout_plan(plan: LayoutPlan, document: SourceDocument) -> None:
    known = {block.id for block in document.blocks}
    required = {block.id for block in document.required_blocks()}
    used = plan.used_block_ids()
    unknown = used - known
    if unknown:
        raise LayoutPlanError(f"unknown block ids: {sorted(unknown)}")
    missing = required - used
    if missing:
        raise LayoutPlanError(f"missing required block ids: {sorted(missing)}")
