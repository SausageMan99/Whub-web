import fitz

from src.content_blocks import ContentBlock, SourceDocument
from src.content_preserving_pipeline import render_best_content_preserving_variant


def test_render_best_content_preserving_variant_outputs_pdf_and_covers_blocks(tmp_path):
    doc = SourceDocument(blocks=[
        ContentBlock.from_text("profile", 1, 0, "Développeur Java", required=True),
        ContentBlock.from_text("experience", 2, 0, "Développement API REST Java Spring", required=True),
    ])
    result = render_best_content_preserving_variant(doc, candidate_first_name="Jérémy", output_dir=tmp_path)

    assert result.final_pdf_path.exists()
    assert result.missing_required_blocks == []
    text = "\n".join(page.get_text("text") for page in fitz.open(result.final_pdf_path))
    assert "Développement API REST Java Spring" in text
