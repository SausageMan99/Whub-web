from src.content_blocks import ContentBlock, SourceDocument
from src.deterministic_layout_planner import build_deterministic_layout_plan
from src.layout_plan import validate_layout_plan


def test_deterministic_plan_uses_all_required_blocks():
    doc = SourceDocument(blocks=[
        ContentBlock.from_text("profile", 1, 0, "Profil", required=True),
        ContentBlock.from_text("skills", 2, 0, "Java AWS", required=True),
        ContentBlock.from_text("experience", 3, 0, "Expérience 1", required=True),
        ContentBlock.from_text("experience", 4, 0, "Expérience 2", required=True),
    ])
    plan = build_deterministic_layout_plan(doc)
    validate_layout_plan(plan, doc)
    assert plan.strategy == "deterministic_content_preserving"


def test_short_metadata_blocks_go_to_sidebar():
    doc = SourceDocument(blocks=[
        ContentBlock.from_text("languages", 1, 0, "Anglais courant", required=True),
        ContentBlock.from_text("experience", 2, 0, "Expérience Java", required=True),
    ])
    plan = build_deterministic_layout_plan(doc)
    sidebar_ids = [
        block_id
        for page in plan.pages
        for zone in page["zones"]
        if zone["zone"] == "right_sidebar"
        for block_id in zone["block_ids"]
    ]
    assert doc.blocks[0].id in sidebar_ids
