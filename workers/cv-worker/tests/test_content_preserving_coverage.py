import fitz

from src.content_blocks import ContentBlock, SourceDocument
from src.content_preserving_rendering import render_content_preserving_pdf
from src.deterministic_layout_planner import build_deterministic_layout_plan
from src.source_coverage import compare_required_block_coverage


def test_rendered_pdf_covers_required_experience_blocks(tmp_path):
    doc = SourceDocument(blocks=[
        ContentBlock.from_text("experience", 1, 0, "Développement API Java Spring AWS", required=True),
        ContentBlock.from_text("experience", 2, 0, "Maintenance applicative SQL Docker", required=True),
    ])
    plan = build_deterministic_layout_plan(doc)
    out = tmp_path / "cv.pdf"
    render_content_preserving_pdf(doc, candidate_first_name="Jérémy", layout_plan=plan, output_path=out)

    rendered = "\n".join(page.get_text("text") for page in fitz.open(out))
    assert compare_required_block_coverage(doc, rendered) == []


def test_coverage_detects_missing_required_experience_block():
    doc = SourceDocument(blocks=[
        ContentBlock.from_text("experience", 1, 0, "Développement API Java Spring AWS", required=True),
        ContentBlock.from_text("experience", 2, 0, "Maintenance applicative SQL Docker", required=True),
    ])
    missing = compare_required_block_coverage(doc, "Développement API Java Spring AWS")
    assert missing == [{"block_id": doc.blocks[1].id, "block_type": "experience", "source_order": 2}]
