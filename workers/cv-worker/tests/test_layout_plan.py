import pytest

from src.content_blocks import ContentBlock, SourceDocument
from src.layout_plan import LayoutPlan, LayoutPlanError, validate_layout_plan


def doc():
    return SourceDocument(blocks=[
        ContentBlock.from_text("profile", 1, 0, "Profil", required=True),
        ContentBlock.from_text("experience", 2, 0, "Expérience Java", required=True),
    ])


def test_layout_plan_valid_when_all_required_blocks_are_used():
    plan = LayoutPlan(strategy="natural", pages=[{"page": 1, "zones": [{"zone": "main", "block_ids": [doc().blocks[0].id, doc().blocks[1].id]}]}])
    validate_layout_plan(plan, doc())


def test_layout_plan_rejects_missing_required_block():
    source = doc()
    plan = LayoutPlan(strategy="bad", pages=[{"page": 1, "zones": [{"zone": "main", "block_ids": [source.blocks[0].id]}]}])
    with pytest.raises(LayoutPlanError, match="missing required block"):
        validate_layout_plan(plan, source)


def test_layout_plan_rejects_unknown_block():
    source = doc()
    plan = LayoutPlan(strategy="bad", pages=[{"page": 1, "zones": [{"zone": "main", "block_ids": ["unknown"]}]}])
    with pytest.raises(LayoutPlanError, match="unknown block"):
        validate_layout_plan(plan, source)
