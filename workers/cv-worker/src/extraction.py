from pathlib import Path
import fitz
from .config import settings
from .supabase_client import client

class ExtractionError(Exception):
    pass


def _page_text_visual_order(page) -> str:
    """Extract page text in visual top-to-bottom order.

    PyMuPDF's plain get_text("text") can follow the PDF internal object order,
    which breaks some designed CVs: missions may appear before their experience
    header. Blocks expose coordinates, so sort them by vertical then horizontal
    position before joining.
    """
    blocks = page.get_text("blocks")
    text_blocks = []
    for block in blocks:
        if len(block) < 5:
            continue
        x0, y0, _x1, _y1, text = block[:5]
        normalized = str(text or "").strip()
        if normalized:
            text_blocks.append((float(y0), float(x0), normalized))
    text_blocks.sort(key=lambda item: (round(item[0], 1), round(item[1], 1)))
    return "\n".join(text for _y, _x, text in text_blocks)


def download_source(job: dict, workdir: Path) -> Path:
    source_path = job["source_file_path"]
    raw = client.storage.from_(settings.cv_sources_bucket).download(source_path)
    local = workdir / "source.pdf"
    local.write_bytes(raw)
    return local

def extract_pdf_text(path: Path) -> str:
    doc = fitz.open(str(path))
    text = "\n".join(_page_text_visual_order(page) for page in doc)
    if len(text.strip()) < 400:
        raise ExtractionError("Texte source trop court: PDF probablement scanné ou illisible")
    return text
