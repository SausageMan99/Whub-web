from pathlib import Path
from dataclasses import dataclass
import re
import fitz
from .config import settings
from .supabase_client import client

class ExtractionError(Exception):
    pass


@dataclass(frozen=True)
class _TextBlock:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


def _sort_blocks(blocks: list[_TextBlock]) -> list[_TextBlock]:
    return sorted(blocks, key=lambda block: (round(block.y0, 1), round(block.x0, 1)))


def _page_text_visual_order(page) -> str:
    """Extract page text in reading order.

    Normal PDFs are sorted top-to-bottom. Sidebar layouts are emitted as
    header/main column first, sidebar second, so skills do not get injected into
    experience bodies.
    """
    raw_blocks = page.get_text("blocks")
    blocks: list[_TextBlock] = []
    for raw in raw_blocks:
        if len(raw) < 5:
            continue
        x0, y0, x1, y1, text = raw[:5]
        normalized = str(text or "").strip()
        if normalized:
            blocks.append(_TextBlock(float(x0), float(y0), float(x1), float(y1), normalized))
    if not blocks:
        return ""

    page_width = float(getattr(getattr(page, "rect", None), "width", 0.0) or 0.0)
    if page_width <= 0:
        page_width = max(block.x1 for block in blocks)
    left_blocks = [block for block in blocks if block.x0 < page_width * 0.34 and block.x1 < page_width * 0.42]
    main_blocks = [block for block in blocks if block.x0 >= page_width * 0.34]
    spanning_blocks = [block for block in blocks if block not in left_blocks and block not in main_blocks]
    if len(left_blocks) >= 4 and len(main_blocks) >= 6:
        header_bottom = min((block.y0 for block in main_blocks), default=0.0)
        header_blocks = [block for block in spanning_blocks if block.y0 <= header_bottom + 2]
        other_spanning = [block for block in spanning_blocks if block not in header_blocks]
        ordered = _sort_blocks(header_blocks) + _sort_blocks(main_blocks + other_spanning) + _sort_blocks(left_blocks)
    else:
        ordered = _sort_blocks(blocks)
    return "\n".join(block.text for block in ordered)


def download_source(job: dict, workdir: Path) -> Path:
    source_path = job["source_file_path"]
    raw = client.storage.from_(settings.cv_sources_bucket).download(source_path)
    local = workdir / "source.pdf"
    local.write_bytes(raw)
    return local

def _normalize_pdf_text_chars(text: str) -> str:
    return (text or "").translate(str.maketrans({
        "ʳ": "r",
        "ᵉ": "e",
        "ᵐ": "m",
        "ᵉ": "e",
        "ᵒ": "o",
        "ᵃ": "a",
    }))


_FOOTER_LINE_RE = re.compile(
    r"^(?:cv\s+cr[ée]é\s+sur|\d+\s*/\s*\d+|\d+\s*/\s*\d+\s+cv\s+cr[ée]é\s+sur)$",
    re.IGNORECASE,
)


def _strip_pdf_footer_lines(text: str) -> str:
    kept: list[str] = []
    for raw in str(text or "").splitlines():
        line = " ".join(raw.split())
        if line and _FOOTER_LINE_RE.match(line):
            continue
        kept.append(raw)
    return "\n".join(kept).strip()


def extract_pdf_text(path: Path) -> str:
    doc = fitz.open(str(path))
    text = _normalize_pdf_text_chars("\n".join(_page_text_visual_order(page) for page in doc))
    text = _strip_pdf_footer_lines(text)
    if len(text.strip()) < 400:
        raise ExtractionError("Texte source trop court: PDF probablement scanné ou illisible")
    return text
