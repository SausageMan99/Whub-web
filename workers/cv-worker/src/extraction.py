from pathlib import Path
from dataclasses import dataclass
import logging
import os
import re
import fitz
from .text_readability import READABILITY_OCR_THRESHOLD, text_readability
from .text_repair import (
    repair_broken_ligatures,
    repair_detached_capitals,
    repair_missing_space_after_punctuation,
    text_vocabulary,
)
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


def _block_box(x0, y0, x1, y1) -> tuple[int, int, int, int]:
    return (round(float(x0)), round(float(y0)), round(float(x1)), round(float(y1)))


def _page_text_visual_order(page, textpage=None, skip_boxes=None) -> str:
    """Extract page text in reading order.

    Normal PDFs are sorted top-to-bottom. Sidebar layouts are emitted as
    header/main column first, sidebar second, so skills do not get injected into
    experience bodies. Blocks whose box is in `skip_boxes` (page furniture,
    see find_page_furniture) are left out.
    """
    raw_blocks = page.get_text("blocks", textpage=textpage) if textpage is not None else page.get_text("blocks")
    blocks: list[_TextBlock] = []
    for raw in raw_blocks:
        if len(raw) < 5:
            continue
        x0, y0, x1, y1, text = raw[:5]
        if skip_boxes and _block_box(x0, y0, x1, y1) in skip_boxes:
            continue
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


# Page furniture (lot 5, 2026-11): running headers and footers of the
# source CV ("<Prénom NOM> · <titre>", "Page 2 / 4", "D O S S I E R  D E
# C O M P É T E N C E S") were read as content and copied into experiences
# and skills. A block lying in the top or bottom band of the page whose text
# (digits ignored) comes back on two pages or more is furniture; so is a
# block made of page numbers only. The page-1 header is kept: it carries the
# name and title the model needs.
_FURNITURE_BAND_RATIO = 0.12
_PAGE_NUMBER_LINE_RE = re.compile(
    r"^(?:page\s*)?\d{1,3}\s*(?:/|sur|of|·|-)\s*\d{1,3}$|^page\s+\d{1,3}$", re.IGNORECASE
)


def _furniture_key(text: str) -> str:
    return re.sub(r"\d+", "#", " ".join(str(text or "").split())).casefold()


def find_page_furniture(doc) -> tuple[dict[int, set[tuple[int, int, int, int]]], list[str]]:
    """({page index: boxes of furniture blocks}, distinct furniture texts)."""
    band_blocks: list[tuple[int, str, tuple[int, int, int, int], str, str]] = []
    pages_by_key: dict[str, set[int]] = {}
    for index, page in enumerate(doc):
        height = float(getattr(getattr(page, "rect", None), "height", 0.0) or 0.0)
        if height <= 0:
            continue
        for raw in page.get_text("blocks"):
            if len(raw) < 5:
                continue
            x0, y0, x1, y1, text = raw[:5]
            text = str(text or "").strip()
            if not text:
                continue
            if float(y1) <= height * _FURNITURE_BAND_RATIO:
                band = "top"
            elif float(y0) >= height * (1 - _FURNITURE_BAND_RATIO):
                band = "bottom"
            else:
                continue
            key = _furniture_key(text)
            band_blocks.append((index, band, _block_box(x0, y0, x1, y1), key, text))
            pages_by_key.setdefault(key, set()).add(index)
    skip: dict[int, set[tuple[int, int, int, int]]] = {}
    texts: list[str] = []
    for index, band, box, key, text in band_blocks:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        page_numbers_only = bool(lines) and all(_PAGE_NUMBER_LINE_RE.match(line) for line in lines)
        repeated = len(pages_by_key.get(key, ())) >= 2
        if page_numbers_only or (repeated and not (index == 0 and band == "top")):
            skip.setdefault(index, set()).add(box)
            for line in lines:
                if not _PAGE_NUMBER_LINE_RE.match(line) and line not in texts:
                    texts.append(line)
    return skip, texts


def detect_page_furniture(path: Path) -> list[str]:
    """Lines of the running headers/footers of a source PDF (best effort)."""
    try:
        doc = fitz.open(str(path))
        return find_page_furniture(doc)[1]
    except Exception as exc:  # noqa: BLE001 - informative only
        log.warning("page furniture detection failed: %s", type(exc).__name__)
        return []


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
        "ﬀ": "ff",
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
        "ﬅ": "st",
        "ﬆ": "st",
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


# Symbol fonts (Wingdings, Symbol) put their bullet glyphs in this private-use
# block; they extract as unprintable characters, often alone on their line.
# Word sub-bullets extract as a lone "o" line, the text on the next line.
_SYMBOL_FONT_BULLET_RE = re.compile(r"^\s*[\uf000-\uf0ff]+\s*")
_LONE_BULLET_LINE_RE = re.compile(r"^\s*[o◦▪■●•➢✓]\s*$")


def _normalize_symbol_font_bullets(text: str) -> str:
    out: list[str] = []
    pending_bullet = False
    for raw in str(text or "").splitlines():
        match = _SYMBOL_FONT_BULLET_RE.match(raw)
        line = raw[match.end():] if match else raw
        if (match and not line.strip()) or _LONE_BULLET_LINE_RE.match(raw):
            pending_bullet = True
            continue
        if pending_bullet and not line.strip():
            continue
        if match or pending_bullet:
            line = "• " + line.strip()
            pending_bullet = False
        out.append(line)
    return "\n".join(out)


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


def _repair_typography(text: str) -> str:
    """Lost ligatures ("di érents"), detached capitals ("L ead"), missing
    space after a full stop ("métiers.Cette"): see src/text_repair.py."""
    text, _ = repair_broken_ligatures(text)
    text, _ = repair_detached_capitals(text, text_vocabulary([text]))
    text, _ = repair_missing_space_after_punctuation(text)
    return text


def _clean_extracted_text(raw: str) -> str:
    return _repair_typography(
        _strip_pdf_footer_lines(_normalize_symbol_font_bullets(_strip_control_chars(_normalize_pdf_text_chars(raw))))
    )


def _ocr_pdf_text(doc) -> str:
    os.environ.setdefault("TESSDATA_PREFIX", "/usr/share/tesseract-ocr/5/tessdata")
    pages = []
    for page in doc:
        textpage = page.get_textpage_ocr(language=_OCR_LANGUAGES, dpi=_OCR_DPI, full=True)
        pages.append(_page_text_visual_order(page, textpage=textpage))
    return _clean_extracted_text("\n".join(pages))


def extract_pdf_text(path: Path) -> str:
    doc = fitz.open(str(path))
    try:
        furniture, _ = find_page_furniture(doc)
    except Exception as exc:  # noqa: BLE001 - never block extraction on this
        log.warning("page furniture detection failed: %s", type(exc).__name__)
        furniture = {}
    text = _clean_extracted_text("\n".join(
        _page_text_visual_order(page, skip_boxes=furniture[index]) if furniture.get(index) else _page_text_visual_order(page)
        for index, page in enumerate(doc)
    ))
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
