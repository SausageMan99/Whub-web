import fitz

from src.content_blocks import ContentBlock, SourceDocument
from src.content_preserving_rendering import render_content_preserving_pdf
from src.deterministic_layout_planner import build_deterministic_layout_plan


def test_render_content_preserving_pdf_keeps_source_text(tmp_path):
    doc = SourceDocument(blocks=[
        ContentBlock.from_text("profile", 1, 0, "Développeur backend Java", required=True),
        ContentBlock.from_text("experience", 2, 0, "Développement d'API REST en Java et Spring", required=True),
    ])
    plan = build_deterministic_layout_plan(doc)
    out = tmp_path / "cv.pdf"

    render_content_preserving_pdf(doc, candidate_first_name="Jérémy", layout_plan=plan, output_path=out)

    pdf = fitz.open(out)
    text = "\n".join(page.get_text("text") for page in pdf)
    assert "Jérémy" in text
    assert "Développement d'API REST en Java et Spring" in text
