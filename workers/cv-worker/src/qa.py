from pathlib import Path
import re
import fitz

CONTACT_PATTERNS = {
    "email": r"@",
    "linkedin": r"linkedin",
    "url": r"https?://|github\.com|\.com\b",
    "phone_fr": r"(?:\+33|\b0[67])(?:[ .-]?\d{2}){4}\b",
}

class QAError(Exception):
    def __init__(self, report: dict):
        super().__init__("QA failed")
        self.report = report

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
    image_sizes = []
    for page in doc:
        for img in page.get_images(full=True):
            pix = fitz.Pixmap(doc, img[0])
            image_sizes.append([pix.width, pix.height])
    has_logo = [1051, 398] in image_sizes
    has_watermark = [1192, 1192] in image_sizes
    report = {
        "passed": not hits and not bad_glyphs and has_logo and has_watermark and doc.page_count > 0,
        "pages": doc.page_count,
        "contact_hits": hits,
        "bad_glyphs": bad_glyphs,
        "has_logo": has_logo,
        "has_watermark": has_watermark,
    }
    if not report["passed"]:
        raise QAError(report)
    return report
