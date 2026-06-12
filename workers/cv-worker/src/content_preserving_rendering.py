from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from xml.sax.saxutils import escape

from .content_blocks import SourceDocument
from .layout_plan import LayoutPlan

WHUB_PURPLE = colors.HexColor("#7001F5")
INK = colors.HexColor("#111110")


def _block_map(document: SourceDocument):
    return {block.id: block for block in document.blocks}


def render_content_preserving_pdf(
    document: SourceDocument,
    *,
    candidate_first_name: str,
    layout_plan: LayoutPlan,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "WhubTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=WHUB_PURPLE,
        spaceAfter=16,
    )
    block_style = ParagraphStyle(
        "WhubBlock",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.4,
        leading=12,
        textColor=INK,
        spaceAfter=10,
    )
    heading = ParagraphStyle(
        "WhubHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=WHUB_PURPLE,
        spaceBefore=10,
        spaceAfter=5,
    )

    blocks = _block_map(document)
    story = [Paragraph(escape(candidate_first_name.strip() or "CV"), title)]
    for page in layout_plan.pages:
        for zone in page.get("zones", []):
            zone_name = str(zone.get("zone", "main")).replace("_", " ").upper()
            story.append(Paragraph(escape(zone_name), heading))
            for block_id in zone.get("block_ids", []):
                block = blocks[str(block_id)]
                html = escape(block.text).replace("\n", "<br/>")
                story.append(Paragraph(html, block_style))
                story.append(Spacer(1, 3))
    doc = SimpleDocTemplate(str(output_path), pagesize=A4, rightMargin=36, leftMargin=36, topMargin=42, bottomMargin=42)
    doc.build(story)
