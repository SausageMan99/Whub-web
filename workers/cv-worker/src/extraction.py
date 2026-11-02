from pathlib import Path
from dataclasses import dataclass
import logging
import os
import re
import fitz
from .text_readability import READABILITY_OCR_THRESHOLD, text_readability
from .config import settings
from .supabase_client import client

log = logging.getLogger(__name__)

_OCR_LANGUAGES = "fra+eng"
_OCR_DPI = 300


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


def _page_text_visual_order(page, textpage=None) -> str:
    """Extract page text in reading order.

    Normal PDFs are sorted top-to-bottom. Sidebar layouts are emitted as
    header/main column first, sidebar second, so skills do not get injected into
    experience bodies.
    """
    raw_blocks = page.get_text("blocks", textpage=textpage) if textpage is not None else page.get_text("blocks")
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


_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _strip_control_chars(text: str) -> str:
    """Replace NUL/C0/DEL control characters with spaces.

    Some source PDFs (broken ToUnicode maps) extract with NUL bytes mixed
    into the text (incident "Benjamin", 2026-09-08: 638 NUL bytes). Those
    bytes later crash ``subprocess`` when the LLM prompt is passed through
    argv (``ValueError: embedded null byte``), before any model call happens.
    ``\\n`` and ``\\t`` are preserved; other control characters become spaces
    so neighbouring words are not glued together.
    """
    return _CONTROL_CHAR_RE.sub(" ", text or "")


def _clean_extracted_text(raw: str) -> str:
    return _strip_pdf_footer_lines(_strip_control_chars(_normalize_pdf_text_chars(raw)))


def _ocr_pdf_text(doc) -> str:
    os.environ.setdefault("TESSDATA_PREFIX", "/usr/share/tesseract-ocr/5/tessdata")
    pages = []
    for page in doc:
        textpage = page.get_textpage_ocr(language=_OCR_LANGUAGES, dpi=_OCR_DPI, full=True)
        pages.append(_page_text_visual_order(page, textpage=textpage))
    return _clean_extracted_text("\n".join(pages))


def extract_pdf_text(path: Path) -> str:
    doc = fitz.open(str(path))
    text = _clean_extracted_text("\n".join(_page_text_visual_order(page) for page in doc))
    native_readability = text_readability(text)
    if len(text.strip()) < 400 or native_readability < READABILITY_OCR_THRESHOLD:
        # Scanned PDFs or broken font maps: the text layer is missing or
        # gibberish, so the model would guess content. OCR the rendered pages.
        try:
            ocr_text = _ocr_pdf_text(doc)
        except Exception as exc:  # noqa: BLE001 - OCR is best effort; fall back to native text
            log.warning("ocr fallback failed: %s", type(exc).__name__)
        else:
            ocr_readability = text_readability(ocr_text)
            log.info(
                "ocr fallback native_chars=%d native_readability=%.2f ocr_chars=%d ocr_readability=%.2f",
                len(text), native_readability, len(ocr_text), ocr_readability,
            )
            if ocr_readability >= READABILITY_OCR_THRESHOLD and len(ocr_text.strip()) >= len(text.strip()) * 0.5:
                text = ocr_text
    if len(text.strip()) < 400:
        raise ExtractionError("Texte source trop court: PDF probablement scanné ou illisible")
    return text
