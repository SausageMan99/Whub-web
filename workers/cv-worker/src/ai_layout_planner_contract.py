from __future__ import annotations

"""
Contrat IA pour le layout planner (content-preserving).

Règle d'or:
- Le plan ne contient AUCUN texte libre. Il ne référence que des block_id (string)
  issus de SourceDocument.
- Toute fonction de ce module rejette toute insertion de texte "généré"
  qui ne soit pas un block_id autorisé.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, ValidationError

from src.content_blocks import ContentBlock, SourceDocument
from src.deterministic_layout_planner import build_deterministic_layout_plan
from src.layout_plan import LayoutPlan, validate_layout_plan

AUTHORIZED_ZONES = {"header", "main", "right_sidebar", "left_sidebar", "footer"}
ALLOWED_STRATEGIES = {
    "natural",
    "compact",
    "sidebar_heavy",
    "experience_first",
    "deterministic_content_preserving",
}
ALLOWED_DENSITIES = {"comfortable", "normal", "compact"}


class AIPlannerContractError(ValueError):
    pass


class AIProposedLayout(BaseModel):
    strategy: Literal[
        "natural",
        "compact",
        "sidebar_heavy",
        "experience_first",
        "deterministic_content_preserving",
    ]
    page_assignments: dict[str, list[str]]
    variant_density: Literal["comfortable", "normal", "compact"]
    rationale: str = Field(max_length=280)
    ai_provider: str
    ai_model: str
    proposed_at: datetime

    model_config = {"str_to_lower": False}

    @field_validator("rationale", "ai_provider", "ai_model", mode="after")
    def _strip_strings(cls, value: str) -> str:
        return value.strip()

    @field_validator("strategy", mode="after")
    def _check_strategy(cls, value: Literal["natural", "compact", "sidebar_heavy", "experience_first", "deterministic_content_preserving"]) -> Literal["natural", "compact", "sidebar_heavy", "experience_first", "deterministic_content_preserving"]:
        if value not in ALLOWED_STRATEGIES:
            raise ValueError(f"invalid strategy: {value}")
        return value

    @field_validator("page_assignments", mode="after")
    def _check_zones(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        bad = set(value) - AUTHORIZED_ZONES
        if bad:
            raise ValueError(f"unauthorized zones: {sorted(bad)}")
        return value

    @classmethod
    def from_deterministic_plan(
        cls,
        plan: LayoutPlan,
        document: SourceDocument,
        *,
        provider: str = "deterministic-fallback",
        model: str = "none",
    ) -> "AIProposedLayout":
        zone_lists: dict[str, set[str]] = {}
        for page in plan.pages:
            for zone in page.get("zones", []):
                name = str(zone.get("zone", "main"))
                ids = [str(block_id) for block_id in zone.get("block_ids", [])]
                zone_lists.setdefault(name, set()).update(ids)

        blocks_by_id = {block.id: block for block in document.blocks}
        candidate_ids = {block_id for ids in zone_lists.values() for block_id in ids}
        header_candidate = next(
            (
                block.id
                for block in document.ordered_blocks()
                if block.id in candidate_ids and block.type in ("name", "title")
            ),
            None,
        )
        if header_candidate:
            for ids in zone_lists.values():
                ids.discard(header_candidate)
            zone_lists["header"] = {header_candidate}

        ordered_assignments: dict[str, list[str]] = {}
        for zone in [z for z in AUTHORIZED_ZONES if z in zone_lists]:
            ordered_assignments[zone] = sorted(
                zone_lists[zone], key=lambda block_id: blocks_by_id[block_id].source_order
            )

        return cls(
            strategy=plan.strategy,
            page_assignments=ordered_assignments,
            variant_density=plan.density,
            rationale="Deterministic fallback plan converted from existing layout",
            ai_provider=provider.strip(),
            ai_model=model.strip(),
            proposed_at=datetime.now(timezone.utc),
        )


def validate_ai_proposal(proposal: AIProposedLayout, document: SourceDocument) -> None:
    if len(proposal.rationale) > 280:
        raise AIPlannerContractError("rationale exceeds 280 characters")

    known_ids = {block.id for block in document.blocks}
    required_ids = {block.id for block in document.required_blocks()}
    used_ids: set[str] = set()
    for block_ids in proposal.page_assignments.values():
        used_ids.update(block_ids)
    unknown = used_ids - known_ids
    if unknown:
        raise AIPlannerContractError(f"unknown block ids: {sorted(unknown)}")

    missing = required_ids - used_ids
    if missing:
        raise AIPlannerContractError(f"missing required block ids: {sorted(missing)}")

    if proposal.variant_density not in ALLOWED_DENSITIES:
        raise AIPlannerContractError("invalid variant_density")

    if not proposal.ai_provider.strip():
        raise AIPlannerContractError("ai_provider must not be empty")
    if not proposal.ai_model.strip():
        raise AIPlannerContractError("ai_model must not be empty")


def proposal_to_layout_plan(proposal: AIProposedLayout, document: SourceDocument) -> LayoutPlan:
    zones = [
        {"name": zone, "block_ids": ids}
        for zone, ids in proposal.page_assignments.items()
    ]
    plan = LayoutPlan(
        strategy=proposal.strategy,
        pages=[{"page_index": 0, "zones": zones}],
        density=proposal.variant_density,
    )
    validate_layout_plan(plan, document)
    return plan
