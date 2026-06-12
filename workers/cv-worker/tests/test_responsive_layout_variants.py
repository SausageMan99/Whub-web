from src.content_blocks import ContentBlock, SourceDocument
from src.layout_plan import validate_layout_plan
from src.responsive_layout_variants import build_layout_variants


def test_build_layout_variants_returns_multiple_valid_plans():
    doc = SourceDocument(blocks=[
        ContentBlock.from_text("profile", 1, 0, "Profil", required=True),
        ContentBlock.from_text("skills", 2, 0, "Java AWS Docker", required=True),
        ContentBlock.from_text("experience", 3, 0, "Expérience Java", required=True),
    ])
    variants = build_layout_variants(doc)
    assert len(variants) >= 3
    assert len({plan.strategy for plan in variants}) == len(variants)
    for plan in variants:
        validate_layout_plan(plan, doc)
