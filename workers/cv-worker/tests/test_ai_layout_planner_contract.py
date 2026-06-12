from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from pydantic import BaseModel, Field, ValidationError

from src.content_blocks import ContentBlock, SourceDocument
from src.deterministic_layout_planner import build_deterministic_layout_plan
from src.layout_plan import LayoutPlan, validate_layout_plan

from src.ai_layout_planner_contract import (
    AIProposedLayout,
    AIPlannerContractError,
    proposal_to_layout_plan,
    validate_ai_proposal,
)


def _make_doc() -> SourceDocument:
    return SourceDocument(
        blocks=[
            ContentBlock.from_text("profile", 1, 0, "John Doe", required=True),
            ContentBlock.from_text("skills", 2, 0, "Python, Go", required=True),
            ContentBlock.from_text("experience", 3, 0, "ENG @ Acme", required=True),
            ContentBlock.from_text("education", 4, 0, "MSc CS", required=True),
        ]
    )


def _base_proposal(document: SourceDocument) -> AIProposedLayout:
    page_assignments: dict[str, list[str]] = {
        "header": [document.blocks[0].id],
        "main": [document.blocks[0].id, document.blocks[2].id, document.blocks[3].id],
        "right_sidebar": [document.blocks[1].id],
    }
    default_rationale = "Deterministic fallback plan converted from existing layout"
    return AIProposedLayout(
        strategy="experience_first",
        page_assignments=page_assignments,
        variant_density="normal",
        rationale=default_rationale,
        ai_provider="deterministic-fallback",
        ai_model="none",
        proposed_at=datetime.now(timezone.utc),
    )


def test_ai_proposal_accepts_valid_proposal() -> None:
    document = _make_doc()
    proposal = _base_proposal(document)
    validate_ai_proposal(proposal, document)


def test_ai_proposal_rejects_unknown_block_id() -> None:
    document = _make_doc()
    proposal = _base_proposal(document)
    proposal.page_assignments["main"].append("__unknown_block_id__")
    with pytest.raises(AIPlannerContractError):
        validate_ai_proposal(proposal, document)


def test_ai_proposal_rejects_missing_required_block() -> None:
    document = _make_doc()
    proposal = _base_proposal(document)
    proposal.page_assignments = {
        "header": [document.blocks[0].id],
        "right_sidebar": [document.blocks[1].id, document.blocks[2].id],
    }
    with pytest.raises(AIPlannerContractError):
        validate_ai_proposal(proposal, document)


def test_ai_proposal_rejects_long_rationale() -> None:
    document = _make_doc()
    proposal = _base_proposal(document)
    proposal.rationale = "a" * 281
    with pytest.raises(AIPlannerContractError):
        validate_ai_proposal(proposal, document)


def test_ai_proposal_rejects_invalid_strategy() -> None:
    with pytest.raises(ValidationError):
        AIProposedLayout(
            strategy="not_a_real_strategy",
            page_assignments={"main": []},
            variant_density="normal",
            rationale="ok",
            ai_provider="p",
            ai_model="m",
            proposed_at=datetime.now(timezone.utc),
        )


def test_proposal_to_layout_plan_roundtrip() -> None:
    document = _make_doc()
    deterministic_plan = build_deterministic_layout_plan(document)
    proposal = AIProposedLayout.from_deterministic_plan(
        deterministic_plan,
        document,
        provider="deterministic-fallback",
        model="none",
    )
    roundtrip_plan = proposal_to_layout_plan(proposal, document)
    validate_layout_plan(roundtrip_plan, document)

    assert roundtrip_plan.strategy == deterministic_plan.strategy
    assert roundtrip_plan.density == deterministic_plan.density
    assert roundtrip_plan.used_block_ids() == deterministic_plan.used_block_ids()


_BLOCK_ID_PATTERN = re.compile(r"^[a-z0-9_]+_[0-9]{3}_[0-9a-f]{8}$")


def test_from_deterministic_plan_does_not_introduce_text() -> None:
    document = _make_doc()
    deterministic_plan = build_deterministic_layout_plan(document)
    proposal = AIProposedLayout.from_deterministic_plan(
        deterministic_plan,
        document,
        provider="deterministic-fallback",
        model="none",
    )

    for block_ids in proposal.page_assignments.values():
        for block_id in block_ids:
            assert _BLOCK_ID_PATTERN.match(block_id), block_id

    for block in document.blocks:
        assert block.text not in proposal.rationale, proposal.rationale

    for zone in proposal.page_assignments:
        assert zone in {
            "header",
            "main",
            "right_sidebar",
            "left_sidebar",
            "footer",
        }
