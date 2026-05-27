from pathlib import Path
from typing import Any, cast
import re
import fitz

CONTACT_PATTERNS = {
    "email": r"@",
    "linkedin": r"linkedin",
    "url": r"https?://|github\.com|\.com\b",
    "phone_fr": r"(?:\+33|\b0[67])(?:[ .-]?\d{2}){4}\b",
}

READABLE_MARGIN_PT = 24
BBOX_TOLERANCE_PT = 1.5

class QAError(Exception):
    def __init__(self, report: dict):
        super().__init__("QA failed")
        self.report = report


def _block_text(block: dict[str, Any]) -> str:
    return "".join(
        span.get("text", "")
        for line in block.get("lines", [])
        for span in line.get("spans", [])
    ).strip()


def find_text_overflow(
    doc: fitz.Document,
    margin: float = READABLE_MARGIN_PT,
    tolerance: float = BBOX_TOLERANCE_PT,
) -> list[dict[str, Any]]:
    """Return text blocks outside the readable page area.

    Only PyMuPDF text blocks (type 0) are inspected, so large logo/watermark
    image blocks cannot create false positives. Coordinates use PDF points.
    """
    findings: list[dict[str, Any]] = []
    for page_index in range(1, doc.page_count + 1):
        page = doc[page_index - 1]
        rect = page.rect
        limits = {
            "left": margin,
            "top": margin,
            "right": rect.width - margin,
            "bottom": rect.height - margin,
        }
        blocks = cast(dict[str, Any], page.get_text("dict")).get("blocks", [])
        for block in blocks:
            if block.get("type") != 0:
                continue
            text = _block_text(block)
            if not text:
                continue
            x0, y0, x1, y1 = block["bbox"]
            checks = [
                ("left", x0, limits["left"], x0 < limits["left"] - tolerance),
                ("top", y0, limits["top"], y0 < limits["top"] - tolerance),
                ("right", x1, limits["right"], x1 > limits["right"] + tolerance),
                ("bottom", y1, limits["bottom"], y1 > limits["bottom"] + tolerance),
            ]
            for side, coordinate, limit, failed in checks:
                if not failed:
                    continue
                findings.append({
                    "page": page_index,
                    "side": side,
                    "coordinate": round(float(coordinate), 2),
                    "limit": round(float(limit), 2),
                    "bbox": [round(float(value), 2) for value in block["bbox"]],
                    "text": text[:160],
                    "message": (
                        f"Texte hors zone lisible page {page_index}: "
                        f"{side}={coordinate:.2f} limite={limit:.2f}"
                    ),
                })
    return findings


def run_qa(pdf_path: Path, forbidden_names: list[str] | None = None) -> dict:
    doc = fitz.open(str(pdf_path))
    text = "\n".join(page.get_text("text") for page in doc)
    hits = []
    for name, pattern in CONTACT_PATTERNS.items():
        if re.search(pattern, text, re.I):
            hits.append(name)
    for name in forbidden_names or []:
        if name and name.lower() in text.lower():
            hits.append(f"forbidden_name:{name}")
    bad_glyphs = any(x in text for x in ["�", "\x00"])
    overflow_hits = find_text_overflow(doc)
    image_sizes = []
    for page in doc:
        for img in page.get_images(full=True):
            pix = fitz.Pixmap(doc, img[0])
            image_sizes.append([pix.width, pix.height])
    has_logo = [1051, 398] in image_sizes
    has_watermark = [1192, 1192] in image_sizes
    report = {
        "passed": not hits and not bad_glyphs and not overflow_hits and has_logo and has_watermark and doc.page_count > 0,
        "pages": doc.page_count,
        "contact_hits": hits,
        "bad_glyphs": bad_glyphs,
        "text_overflow_hits": overflow_hits,
        "has_logo": has_logo,
        "has_watermark": has_watermark,
    }
    if not report["passed"]:
        raise QAError(report)
    return report
