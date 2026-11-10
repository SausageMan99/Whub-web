#!/usr/bin/env python3
"""Render a W hub client-facing candidate CV from structured JSON.

Usage:
  python workers/cv-worker/renderer/whub_cv_renderer.py input.json output.pdf

The JSON must contain only information copied from the candidate's original CV.
Do not include candidate phone/email/linkedin: W hub client CVs must not expose direct contact details.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageChops
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

W, H = A4
BLACK = HexColor('#000000')
TITLE = HexColor('#241D19')
PURPLE = HexColor('#7001F5')

WORKER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSETS_DIR = WORKER_ROOT / 'assets' / 'whub'
DEFAULT_FONTS_DIR = WORKER_ROOT / 'assets' / 'fonts' / 'poppins'
EXPECTED_ASSET_SIZES = {
    'img_0dcab6df734b.png': (1051, 398),
    'img_90df8f14aa40.png': (1192, 1192),
}
EXPECTED_FONT_SHA256 = {
    'Regular': '7e65201e9b79159e2300267cc885e16c8dcef2424cdfa09a29bfb0980a94a7ba',
    'Bold': '983676516167748b74de6f4771fb384c664fd913acb8b471122ecacf5da5ea6c',
    'SemiBold': 'd3bf1bdaf0550e83da9ac0b1d1d9fe6db086835a83aa28578e609a394b9a0286',
    'Light': '650ba57fa99d12ec40c31ccfb680be656be4497fbe14164617d67e32ffe9cd46',
}
REQUIRED_FONT_WEIGHTS = tuple(EXPECTED_FONT_SHA256)
ASSETS_DIR = Path(os.environ.get('WHUB_ASSETS_DIR', DEFAULT_ASSETS_DIR))
LOGO_SRC = ASSETS_DIR / 'img_0dcab6df734b.png'
WM_SRC = ASSETS_DIR / 'img_90df8f14aa40.png'
LOGO = Path('/tmp/whub_logo_renderer.png')
WM = Path('/tmp/whub_watermark_renderer.png')

CONTACT_PATTERNS = [
    # Email or explicit URL schemes are direct contact markers in this renderer input.
    # Do not block every '@': project/product names such as "Th@Bot" are valid CV content.
    re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I),
    re.compile(r'https?://'),
    # Candidate profile URLs often arrive without protocol after LLM structuring.
    re.compile(r'\b(?:www\.)?github\.com\b'),
    re.compile(r'\b(?:www\.)?(?:[a-z]{2}\.)?linkedin\.com\b'),
    re.compile(r'\blinkedin\s*/\s*in\b'),
    # LinkedIn is rarely a technical skill in W hub CV JSON; keep it blocked as contact surface.
    re.compile(r'\blinkedin\b'),
    # Bare GitHub can be a technical tool, so only block contact-like forms: label/path/handle.
    re.compile(r'\bgithub\b\s*(?::|/|@)\s*(?!gitlab\b)[\w.-]+'),
]
PHONE_RE = re.compile(r'(?<!\d)(?:\+33\s?|0)[67](?:[\s.\-]?\d{2}){4}(?!\d)')


def die(msg: str) -> None:
    print(f'ERROR: {msg}', file=sys.stderr)
    sys.exit(1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_poppins() -> Path:
    font_dir = Path(os.environ['WHUB_FONTS_DIR']) if 'WHUB_FONTS_DIR' in os.environ else DEFAULT_FONTS_DIR
    missing = [f'Poppins-{w}.ttf' for w in REQUIRED_FONT_WEIGHTS if not (font_dir / f'Poppins-{w}.ttf').is_file()]
    if missing:
        source = 'configured WHUB_FONTS_DIR' if 'WHUB_FONTS_DIR' in os.environ else 'default fonts dir'
        die(f"Poppins fonts incomplete in {source} {font_dir}: missing {', '.join(missing)}")
    for weight in REQUIRED_FONT_WEIGHTS:
        path = font_dir / f'Poppins-{weight}.ttf'
        actual_sha256 = sha256(path)
        expected_sha256 = EXPECTED_FONT_SHA256[weight]
        if actual_sha256 != expected_sha256:
            die(
                f'Poppins font divergent in {font_dir}: {path} '
                f'sha256={actual_sha256}, expected {expected_sha256}'
            )
    return font_dir


def assert_asset_size(path: Path, expected: tuple[int, int]) -> None:
    actual = Image.open(path).size
    if actual != expected:
        die(f'Invalid W hub asset dimensions for {path}: {actual}, expected {expected}')


def register_fonts(font_dir: Path) -> None:
    pdfmetrics.registerFont(TTFont('Poppins', str(font_dir / 'Poppins-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('Poppins-Bold', str(font_dir / 'Poppins-Bold.ttf')))
    pdfmetrics.registerFont(TTFont('Poppins-SemiBold', str(font_dir / 'Poppins-SemiBold.ttf')))
    pdfmetrics.registerFont(TTFont('Poppins-Light', str(font_dir / 'Poppins-Light.ttf')))


def trim_transparent(src: Path, dst: Path, threshold: int = 8, watermark: bool = False) -> None:
    im = Image.open(src).convert('RGBA')
    rgb = im.convert('RGB')
    diff = ImageChops.difference(rgb, Image.new('RGB', im.size, (255, 255, 255))).convert('L')
    mask = diff.point(lambda p: 255 if p > threshold else 0)
    bbox = mask.getbbox() or (0, 0, *im.size)
    im = im.crop(bbox)
    data = []
    for r, g, b, a in im.getdata():
        if watermark:
            if r > 252 and g > 252 and b > 252:
                data.append((255, 255, 255, 0))
            else:
                data.append((238, 238, 238, 52))
        else:
            if r > 245 and g > 245 and b > 245:
                data.append((255, 255, 255, 0))
            else:
                data.append((r, g, b, a))
    im.putdata(data)
    im.save(dst)


def prep_assets() -> None:
    if not LOGO_SRC.exists() or not WM_SRC.exists():
        die(f'W hub logo/watermark images missing from {ASSETS_DIR}')
    assert_asset_size(LOGO_SRC, EXPECTED_ASSET_SIZES[LOGO_SRC.name])
    assert_asset_size(WM_SRC, EXPECTED_ASSET_SIZES[WM_SRC.name])
    trim_transparent(LOGO_SRC, LOGO, 8, False)
    trim_transparent(WM_SRC, WM, 1, True)


UNSUPPORTED_TEXT_REPLACEMENTS = {
    '\u2192': '->',
    '\u27f6': '->',
    '\u2794': '->',
    '\uf0e0': '->',
}


def normalize_render_text(value) -> str:
    text = str(value)
    for source, replacement in UNSUPPORTED_TEXT_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    return text


def html(s: str) -> str:
    return escape(normalize_render_text(s)).replace('\n', '<br/>')


def spaced(s: str) -> str:
    return ' '.join(list(s.upper()))


def purple(s: str) -> str:
    return f'<font color="#7001F5">{escape(str(s))}</font>'


def has_contact(value) -> bool:
    text = json.dumps(value, ensure_ascii=False).lower()
    return any(pattern.search(text) for pattern in CONTACT_PATTERNS) or bool(PHONE_RE.search(text))


def _looks_like_full_name_display(name: str) -> bool:
    tokens = [token for token in re.split(r"\s+", str(name or "").strip()) if re.search(r"[A-Za-zÀ-ÿ]", token)]
    return len(tokens) >= 2


def _normalize_guard_text(value: str) -> str:
    normalized = re.sub(r"[–—−]", "-", str(value or "").lower().replace("’", "'"))
    normalized = re.sub(r"[^a-z0-9+#+àâäéèêëîïôöùûüç]+", " ", normalized)
    return " " + re.sub(r"\s+", " ", normalized).strip() + " "


def has_forbidden_identity(value, forbidden_terms=None) -> bool:
    name = value.get('name') if isinstance(value, dict) else None
    if _looks_like_full_name_display(str(name or '')):
        return True
    terms = [str(term).strip() for term in (forbidden_terms or []) if str(term).strip()]
    if not terms:
        return False
    text = _normalize_guard_text(json.dumps(value, ensure_ascii=False))
    for term in terms:
        normalized_term = _normalize_guard_text(term).strip()
        if normalized_term and re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", text):
            return True
    return False


SKILL_ITEM_SPLIT_RE = re.compile(r"\s*[;,]\s*")
DEFAULT_MAX_SKILL_ITEM_CHARS = 125
# Pagination by measured height (lot 1, 2026-11). The page breaks are decided
# on the room really left on the page, never on a character count: a full
# width page holds ~4 400 characters, a density budget of 2 850 left pages
# half empty.
# A section heading needs at least this many body lines under it on the same
# page (or fewer when the section is shorter)...
MIN_LINES_UNDER_HEADING = 2
# Gap after each experience block, normal / compact spacing profile.
EXPERIENCE_GAP = 13.0
COMPACT_EXPERIENCE_GAP = 7.0
# ...and an experience (date + role) at least this many body lines.
MIN_EXPERIENCE_OPENER_LINES = 3
# A paragraph (bullet) split across two pages keeps this many lines each side.
MIN_SPLIT_LINES = 2
# A section continued on the next page ("Missions clés (suite)") carries at
# least this many lines there: a two-line "(suite)" reads as a leftover.
MIN_CONTINUATION_LINES = 3
# Fill of a page = bottom of its flow text over the readable zone (36 pt
# margins), the measure QA reads on the PDF (qa.collect_pagination_metrics).
FILL_ZONE_TOP = 36.0
# The last page is rebalanced when it holds less than this share of a page...
LAST_PAGE_MIN_FILL = 0.35
# ...towards this share, without bringing the previous page under this one.
LAST_PAGE_TARGET_FILL = 0.42
PENULTIMATE_MIN_FILL = 0.65
# Page 1 is what the client sees first: it gives up a few lines at most.
FIRST_PAGE_MIN_FILL_WHEN_BALANCING = 0.85
# "Formation & Diplômes" column of page 1 (lot 3): it starts under its
# title and stops above the page bottom; what does not fit continues full
# width after the experiences (Renderer.plan_sidebar).
SIDEBAR_X = 431.6
SIDEBAR_WIDTH = 138
SIDEBAR_TOP = 270.0
SIDEBAR_BOTTOM_MARGIN = 2.0
# Room above a section title opened in the flow (projects, sidebar
# continuation): its capitals sit above the y it is drawn at.
SECTION_TITLE_LEAD = 14.0
# Logo of every page (Renderer.brand): x 424-545, y 43-88.
LOGO_LEFT = 424
LOGO_BAND_BOTTOM = 92
# Lot 2 (2026-11): a category is drawn as one block under one title. Chunks
# of 8 items each labelled "X (suite)" printed "Autres (suite)" up to 13 times
# on page 1. Only a category taller than the room left in its column is
# continued (split_skill_columns_for_page), once.
DEFAULT_MAX_SKILL_ITEMS_PER_BLOCK = 1000
DEFAULT_MAX_SKILL_BLOCK_CHARS = 100000


def _compact_skill_chunk(parts: list[str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for part in parts:
        cleaned = str(part).strip(" \t\n;,•")
        if not cleaned:
            continue
        candidate = cleaned if not current else f"{current}, {cleaned}"
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = cleaned
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def split_skill_item_non_destructively(item, max_chars: int = DEFAULT_MAX_SKILL_ITEM_CHARS) -> list[str]:
    """Split separator-heavy skill bullets into readable chunks without dropping terms.

    The renderer may improve layout density, but it must not rewrite the stack or
    silently remove technologies. If a long text has no safe separators, keep it
    intact so QA can still flag it instead of inventing a rewrite.
    """
    text = normalize_render_text(str(item)).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    if text.count(";") + text.count(",") < 2:
        return [text]
    pieces = [piece for piece in SKILL_ITEM_SPLIT_RE.split(text) if piece.strip()]
    chunks = _compact_skill_chunk(pieces, max_chars)
    return chunks or [text]


def prepare_readable_skill_categories(
    skills,
    *,
    max_item_chars: int = DEFAULT_MAX_SKILL_ITEM_CHARS,
    max_items_per_block: int = DEFAULT_MAX_SKILL_ITEMS_PER_BLOCK,
    max_block_chars: int = DEFAULT_MAX_SKILL_BLOCK_CHARS,
):
    """Return renderer-only skill chunks for readable columns/pages.

    This is intentionally non-destructive: source order inside each category is
    preserved, duplicates are not removed, and continuation blocks are labelled
    `(suite)` rather than hiding overflow. Only layout shape changes.
    """
    prepared = []
    for raw_cat in skills or []:
        if not isinstance(raw_cat, dict):
            continue
        category = str(raw_cat.get('category', '')).strip()
        expanded_items: list[str] = []
        for item in raw_cat.get('items') or []:
            expanded_items.extend(split_skill_item_non_destructively(item, max_chars=max_item_chars))
        if not category and not expanded_items:
            continue
        if not expanded_items:
            prepared.append({'category': category, 'items': []})
            continue

        chunk: list[str] = []
        chunk_chars = 0
        chunk_index = 0
        for index, item in enumerate(expanded_items):
            projected_chars = chunk_chars + len(item) + (2 if chunk else 0)
            remaining_after_current = len(expanded_items) - index - 1
            should_split_for_count = len(chunk) >= max_items_per_block and remaining_after_current > 0
            if chunk and (should_split_for_count or projected_chars > max_block_chars):
                prepared.append({
                    'category': category if chunk_index == 0 else f'{category} (suite)',
                    'items': chunk,
                })
                chunk_index += 1
                chunk = []
                chunk_chars = 0
            chunk.append(item)
            chunk_chars += len(item) + (2 if len(chunk) > 1 else 0)
        if chunk:
            prepared.append({
                'category': category if chunk_index == 0 else f'{category} (suite)',
                'items': chunk,
            })
    return prepared


class Renderer:
    def __init__(self, out, layout_options: dict | None = None, page_flow_limits: dict | None = None):
        self.c = canvas.Canvas(out, pagesize=A4, initialFontName='Poppins', initialFontSize=8)
        self.page = 0
        self.layout_options = layout_options or {}
        # Explicit placement requests (revision hints). The default packing
        # no longer sets them: breaks follow the measured room on the page.
        self.force_experiences_new_page = bool(self.layout_options.get('force_experiences_new_page'))
        self.force_page_break_before_experience_indexes = set(
            int(i) for i in self.layout_options.get('force_page_break_before_experience_indexes', [])
            if str(i).lstrip('-').isdigit()
        )
        self.allow_grouping = bool(self.layout_options.get('allow_grouping', True))
        self.min_lines_under_heading = max(1, int(self.layout_options.get('min_lines_under_heading', MIN_LINES_UNDER_HEADING)))
        self.min_experience_opener_lines = max(
            self.min_lines_under_heading,
            int(self.layout_options.get('min_experience_opener_lines', MIN_EXPERIENCE_OPENER_LINES)),
        )
        # Spacing profile (lot 4, 2026-11): "compact" tightens line spacing and
        # the gaps between blocks, never the font sizes. Tried as a layout
        # variant when a CV can drop a page or a reviewer asks for fewer pages.
        self.compact = str(self.layout_options.get('spacing') or '') == 'compact'
        self.experience_gap = COMPACT_EXPERIENCE_GAP if self.compact else EXPERIENCE_GAP
        self.current_page_chars = 0
        # page number -> lowest y the experience flow may reach on that page
        # (tail balancing, see render_document).
        self.page_flow_limits = {int(k): float(v) for k, v in (page_flow_limits or {}).items()}
        # page number -> bottom of the flow text drawn on that page.
        self.page_flow_bottoms: dict[int, float] = {}
        self.page_start_y = 55
        self.sidebar_overflow = []
        self.left = 59.5
        self.right = 535.8
        self.bottom = 36
        self.content_bottom = H - self.bottom
        self.fx = self.left
        self.fw = self.right - self.left
        self.y = 55
        self.styles()

    def styles(self):
        self.body = ParagraphStyle('body', fontName='Poppins-Light', fontSize=8.35, leading=10.25, textColor=BLACK, spaceAfter=1.2)
        self.bul = ParagraphStyle('bul', parent=self.body, leftIndent=15, firstLineIndent=-7, fontSize=8.25, leading=10.15, spaceAfter=0.25)
        # Second part of a bullet split across pages: aligned on the bullet text.
        self.bul_cont = ParagraphStyle('bul_cont', parent=self.bul, firstLineIndent=0)
        self.date = ParagraphStyle('date', parent=self.body, fontName='Poppins-Bold', fontSize=9.0, leading=11.0, textColor=PURPLE, spaceBefore=2.0, spaceAfter=1.0)
        self.role = ParagraphStyle('role', parent=self.body, fontName='Poppins-Bold', fontSize=8.8, leading=10.6, spaceAfter=1.2)
        self.sub = ParagraphStyle('sub', parent=self.body, fontName='Poppins-Bold', fontSize=8.45, leading=10.2, spaceBefore=2.8, spaceAfter=0.5)
        self.side = ParagraphStyle('side', parent=self.body, fontName='Poppins-Light', fontSize=8.75, leading=11.35, spaceAfter=0.3)
        self.side_b = ParagraphStyle('side_b', parent=self.side, fontName='Poppins-Bold')
        self.skill = ParagraphStyle('skill', parent=self.body, fontName='Poppins-Light', fontSize=8.0, leading=9.55, spaceAfter=0.1)
        self.skill_head = ParagraphStyle('skill_head', parent=self.body, fontName='Poppins-Bold', fontSize=8.35, leading=10.0, spaceBefore=1.2, spaceAfter=0.2)
        # Client-facing skills are a scan map, not an ATS bullet inventory.
        # Render one compact line per category to avoid multi-page skills dumps
        # while preserving every item in the structured JSON.
        self.skill_inline = ParagraphStyle('skill_inline', parent=self.body, fontName='Poppins-Light', fontSize=7.85, leading=9.15, spaceAfter=1.5)
        self.desc = ParagraphStyle('desc', parent=self.body, fontName='Poppins-Light', fontSize=7.85, leading=9.55, spaceAfter=1.0)
        if self.compact:
            for style, leading, space_before, space_after in (
                (self.body, 9.75, None, 0.8),
                (self.bul, 9.6, None, 0.1),
                (self.bul_cont, 9.6, None, 0.1),
                (self.date, 10.6, 1.0, 0.6),
                (self.role, 10.2, None, 0.6),
                (self.sub, 9.9, 1.6, 0.3),
                (self.desc, 9.2, None, 0.6),
            ):
                style.leading = leading
                style.spaceAfter = space_after
                if space_before is not None:
                    style.spaceBefore = space_before

    def image_top(self, path: Path, x: float, y: float, w: float, h: float) -> None:
        self.c.drawImage(str(path), x, H - y - h, width=w, height=h, mask='auto', preserveAspectRatio=True)

    def brand(self, first=False):
        self.image_top(LOGO, LOGO_LEFT, 43, 121, 45)
        self.image_top(WM, 150 if first else 185, 315 if first else 285, 285, 285)

    def new_page(self, first=False, name=''):
        if self.page:
            self.c.showPage()
        self.page += 1
        self.current_page_chars = 0
        self.brand(first)
        if not first:
            self.text(name.upper(), self.left, 44, 'Poppins-Bold', 8.3, PURPLE)
            self.y = 82
        else:
            self.y = 55
        self.page_start_y = self.y

    def text(self, s, x, y, font, size, color=BLACK):
        self.c.setFillColor(color)
        self.c.setFont(font, size)
        self.c.drawString(x, H - y, str(s))
        self._track_page_text(s)

    def line(self, x1, y1, x2, y2, color=BLACK, width=.55):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        self.c.line(x1, H - y1, x2, H - y2)

    def section_at(self, title, x, y, w, size=15):
        label = spaced(title)
        self.text(label, x, y, 'Poppins-SemiBold', size, TITLE)
        self.line(x, y + 5.2, x + min(w, pdfmetrics.stringWidth(label, 'Poppins-SemiBold', size) + 6), y + 5.2, TITLE, .55)
        return y + 25

    def para_at(self, s, x, y, w, style):
        return self.para_html_at(html(s), x, y, w, style)

    def para_html_at(self, html_text, x, y, w, style):
        p = Paragraph(html_text, style)
        _, h = p.wrap(w, 10000)
        p.drawOn(self.c, x, H - y - h)
        self._track_page_text(html_text)
        return y + h + style.spaceAfter

    def flow(self, x, y, w):
        self.fx, self.y, self.fw = x, y, w

    def measurep(self, html_text, style, w=None):
        p = Paragraph(html_text, style)
        _, h = p.wrap(w or self.fw, 10000)
        return h + style.spaceAfter

    def measure_text(self, s, style, w=None):
        return self.measurep(html(s), style, w)

    def ensure_space(self, height, name=None):
        if self.y + height > self._flow_bottom() and not self._at_page_top():
            self._continue_on_new_page(name)
            return True
        return False

    @staticmethod
    def _plain_len(text) -> int:
        plain = re.sub(r'<[^>]+>', ' ', str(text))
        return len(re.sub(r'\s+', ' ', plain).strip())

    def _track_page_text(self, text) -> None:
        self.current_page_chars += self._plain_len(text)

    # ------------------------------------------------------------ flow helpers

    def _flow_bottom(self) -> float:
        """Lowest y the experience flow may reach on the current page."""
        return min(self.content_bottom, self.page_flow_limits.get(self.page, self.content_bottom))

    def _at_page_top(self) -> bool:
        return self.y <= self.page_start_y + 1

    def _continue_on_new_page(self, name=None) -> None:
        self.new_page(False, name or self.current_name)
        self.flow(self.left, self.y, self.right - self.left)

    def _mark_flow_bottom(self, y: float) -> None:
        self.page_flow_bottoms[self.page] = max(self.page_flow_bottoms.get(self.page, 0.0), y)

    def _page_fill(self, page: int) -> float:
        bottom = self.page_flow_bottoms.get(page, FILL_ZONE_TOP)
        return max(0.0, (bottom - FILL_ZONE_TOP) / (self.content_bottom - FILL_ZONE_TOP))

    def _lines_of(self, html_text, style, width=None) -> int:
        p = Paragraph(html_text, style)
        _, h = p.wrap(width or self.fw, 10000)
        return max(1, int(round(h / style.leading)))

    def _draw_paragraph(self, html_text, style, max_lines=None):
        """Draw a paragraph at the flow position; with max_lines, draw only its
        first lines and return the html of the rest (None when all drawn)."""
        p = Paragraph(html_text, style)
        _, h = p.wrap(self.fw, 10000)
        if max_lines is not None and h > max_lines * style.leading + 0.5:
            pieces = self._split_html_at_lines(html_text, style, max_lines)
            if pieces:
                first_html, rest_html = pieces
                first = Paragraph(first_html, style)
                _, ph = first.wrap(self.fw, 10000)
                first.drawOn(self.c, self.fx, H - self.y - ph)
                self._track_page_text(first_html)
                self._mark_flow_bottom(self.y + ph)
                self.y += ph + style.spaceAfter
                return rest_html
        p.drawOn(self.c, self.fx, H - self.y - h)
        self._track_page_text(html_text)
        self._mark_flow_bottom(self.y + h)
        self.y += h + style.spaceAfter
        return None

    def _split_html_at_lines(self, html_text, style, max_lines, width=None):
        """(first, rest) html of a paragraph cut after its first max_lines
        lines, on a word boundary; None when it cannot be cut safely.

        ReportLab's Paragraph.split pieces return '' from getPlainText, so the
        rest of a split bullet used to vanish: the cut is computed on the
        words of the source html instead (bullets and text are escaped plain
        text; markup with attributes is never cut)."""
        if '<font' in html_text or max_lines < 1:
            return None
        words = html_text.split(' ')
        lo, hi = 0, len(words)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._lines_of(' '.join(words[:mid]), style, width) <= max_lines:
                lo = mid
            else:
                hi = mid - 1
        if lo <= 0 or lo >= len(words):
            return None
        first, rest = ' '.join(words[:lo]), ' '.join(words[lo:]).strip()
        if not rest or not first.strip() or first.strip() == '•':
            return None
        return first, rest

    def drawp(self, html_text, style):
        """Draw a paragraph in the current flow, splitting across pages if needed
        (date, role, skill overflow lines). Returns True when a page was added."""
        page_changed = False
        remaining_html = html_text
        while remaining_html is not None:
            p = Paragraph(remaining_html, style)
            _, h = p.wrap(self.fw, 10000)
            avail = self._flow_bottom() - self.y
            if h <= avail:
                self._draw_paragraph(remaining_html, style)
                return page_changed
            lines_fit = int(avail // style.leading)
            if lines_fit < MIN_SPLIT_LINES or self._lines_of(remaining_html, style) - lines_fit < MIN_SPLIT_LINES:
                if self._at_page_top():
                    # Taller than a page: split anyway rather than loop.
                    lines_fit = max(1, lines_fit)
                else:
                    self._continue_on_new_page()
                    page_changed = True
                    continue
            if self._split_html_at_lines(remaining_html, style, lines_fit) is None:
                if not self._at_page_top():
                    self._continue_on_new_page()
                    page_changed = True
                    continue
                self._draw_paragraph(remaining_html, style)
                return page_changed
            remaining_html = self._draw_paragraph(remaining_html, style, max_lines=lines_fit)
            if remaining_html is not None:
                self._continue_on_new_page()
                page_changed = True
        return page_changed

    def p(self, s):
        self.drawp(html(s), self.body)

    def bullet(self, s):
        self.drawp('• ' + html(s), self.bul)

    def _heading_width(self) -> float:
        """Width for a heading drawn here: at the top of a continuation page
        the first line runs beside the W hub logo (x >= LOGO_LEFT, y < 88),
        so a long "Heading (suite)" wraps before it."""
        if self.page > 1 and self.y < LOGO_BAND_BOTTOM:
            return min(self.fw, LOGO_LEFT - 10 - self.fx)
        return self.fw

    def subhead(self, s):
        width = self._heading_width()
        if width >= self.fw:
            return self.drawp(html(s), self.sub)
        saved = self.fw
        self.fw = width
        try:
            return self.drawp(html(s), self.sub)
        finally:
            self.fw = saved

    # ------------------------------------------------------------ sections

    def _section_paragraphs(self, sec):
        """(style, [(html, style)]) of a section body, in source order."""
        content = sec.get('content', '')
        if isinstance(content, list):
            items = [str(item) for item in content if str(item).strip()]
            return self.bul, [('• ' + html(item), self.bul) for item in items]
        if content:
            return self.body, [(html(str(content)), self.body)]
        return self.body, []

    def _section_lines(self, sec, width=None) -> int:
        _, paras = self._section_paragraphs(sec)
        return sum(self._lines_of(text, style, width) for text, style in paras)

    def _continuation_lines(self, paras, full, partial, width, next_width) -> int:
        """Lines the rest of a section takes on the next page, drawn at
        next_width, when `full` paragraphs and `partial` lines stay here."""
        rest = list(paras[full:])
        if partial and rest:
            text, style = rest[0]
            pieces = self._split_html_at_lines(text, style, partial, width)
            if pieces:
                cont_style = self.bul_cont if style in (self.bul, self.bul_cont) else style
                rest[0] = (pieces[1], cont_style)
        return sum(self._lines_of(text, style, next_width) for text, style in rest)

    def _place_section_here(self, heading_text, paras, avail, width=None):
        """How the section fits in `avail` points: (full, partial, placed, total)
        or None when its heading would be left without enough lines."""
        heading_width = width if width is not None else self._heading_width()
        heading_h = self.measure_text(heading_text, self.sub, heading_width) if heading_text else 0.0
        counts = [self._lines_of(text, style, width) for text, style in paras]
        style = paras[0][1]
        # Page 1 flows in the narrow left column; its continuation is drawn
        # full width, where the same words take fewer lines.
        current_width = width or self.fw
        full_width = self.right - self.left
        min_continuation = MIN_CONTINUATION_LINES
        full, partial, placed = plan_section_break(
            counts, style.leading, style.spaceAfter, avail - heading_h,
            min_split=MIN_SPLIT_LINES, min_continuation=min_continuation,
        )
        if current_width < full_width - 1 and 0 < placed < sum(counts):
            if self._continuation_lines(paras, full, partial, current_width, full_width) < MIN_CONTINUATION_LINES:
                min_continuation = math.ceil(MIN_CONTINUATION_LINES * full_width / current_width)
                full, partial, placed = plan_section_break(
                    counts, style.leading, style.spaceAfter, avail - heading_h,
                    min_split=MIN_SPLIT_LINES, min_continuation=min_continuation,
                )
        total = sum(counts)
        if partial and self._split_html_at_lines(paras[full][0], paras[full][1], partial) is None:
            # Cannot be cut safely (markup): that paragraph moves whole.
            partial, placed = 0, sum(counts[:full])
            if 0 < total - placed < min_continuation:
                placed = 0
        needed = min(self.min_lines_under_heading, total) if heading_text else 1
        if placed < needed:
            return None
        return full, partial, placed, total

    def render_section(self, sec, opens_experience=False):
        """Draw one experience section, breaking pages only between lines that
        keep the heading with its first lines, a split bullet with two lines on
        each side and a continuation with three lines at least.

        opens_experience is kept for compatibility: the opener is checked once
        in maybe_break_before_experience."""
        heading = sec.get('heading')
        _, paras = self._section_paragraphs(sec)
        if not paras:
            if heading:
                self.ensure_space(self.measure_text(heading, self.sub) + self.body.leading * self.min_lines_under_heading)
                self.subhead(heading)
            return
        first = True
        while paras:
            heading_text = heading if first else (f'{heading} (suite)' if heading else None)
            placement = self._place_section_here(heading_text, paras, self._flow_bottom() - self.y)
            if placement is None and not self._at_page_top():
                self._continue_on_new_page()
                continue
            if heading_text:
                self.subhead(heading_text)
            if placement is None:
                # Fresh page and still too tall: fill it line by line.
                text, style = paras.pop(0)
                self.drawp(text, style)
                first = False
                continue
            full, partial, _placed, _total = placement
            for text, style in paras[:full]:
                self._draw_paragraph(text, style)
            rest = paras[full:]
            if partial:
                text, style = rest[0]
                remainder = self._draw_paragraph(text, style, max_lines=partial)
                cont_style = self.bul_cont if style in (self.bul, self.bul_cont) else style
                rest = ([(remainder, cont_style)] if remainder else []) + rest[1:]
            paras = rest
            first = False
            if paras:
                self._continue_on_new_page()

    def render_bullet_list(self, heading, items, opener_items=0):
        self.render_section({'heading': heading, 'content': list(items or [])})

    def render_text_section(self, heading, content):
        self.render_section({'heading': heading, 'content': content})

    def skill_block_height(self, cat, width):
        return self.measurep(self.skill_line_html(cat), self.skill_inline, width) + 4

    def skill_line_html(self, cat):
        category = str(cat.get('category', '') or '').strip()
        items = [str(item).strip() for item in cat.get('items', []) if str(item).strip()]
        if category and items:
            return f"<font name=\"Poppins-Bold\">{html(category)}</font><br/>{html(' · '.join(items))}"
        if category:
            return f"<font name=\"Poppins-Bold\">{html(category)}</font>"
        return html(' · '.join(items))

    def split_skill_columns_for_page(self, skills, start_y, bottom_y):
        widths = [156, 152]
        fitting = [[], []]
        used_heights = [0.0, 0.0]
        capacity = bottom_y - start_y
        overflow = []

        # Layout intelligence: distribute categories by measured rendered height instead
        # of alternating indexes. Largest blocks are placed first so one tall category
        # does not force a needless "Compétences techniques (suite)" page while the
        # opposite column still has room.
        measured = []
        for index, cat in enumerate(skills):
            measured.append((max(self.skill_block_height(cat, width) for width in widths), index, cat))
        total_measured_height = sum(height for height, _, _ in measured)
        target_first_column_height = min(capacity, total_measured_height / 2.0)

        for _, _, raw_cat in measured:
            cat = dict(raw_cat)
            full_heights = [self.skill_block_height(cat, width) for width in widths]
            preferred = 0 if not fitting[0] or used_heights[0] + min(full_heights) <= target_first_column_height else 1
            fit_candidates = [
                idx for idx in [preferred, 1 - preferred]
                if used_heights[idx] + full_heights[idx] <= capacity
            ]
            if fit_candidates:
                col_idx = fit_candidates[0]
                fitting[col_idx].append(cat)
                used_heights[col_idx] += full_heights[col_idx]
                continue

            # Only split a category when no full-category placement fits. This keeps
            # category blocks intact whenever balancing can solve the page fit.
            split_candidates = []
            for idx, width in enumerate(widths):
                remaining = capacity - used_heights[idx]
                header_h = self.measure_text(cat.get('category', ''), self.skill_head, width)
                items = list(cat.get('items', []))
                if not items:
                    continue
                first_h = self.measure_text('• ' + str(items[0]), self.skill, width)
                if remaining >= header_h + first_h:
                    split_candidates.append((remaining, idx, width))
            if split_candidates:
                _, col_idx, width = max(split_candidates)
                items = list(cat.get('items', []))
                kept, rest = [], []
                test_height = used_heights[col_idx] + self.measure_text(cat.get('category', ''), self.skill_head, width)
                for item in items:
                    item_h = self.measure_text('• ' + str(item), self.skill, width)
                    if test_height + item_h <= capacity:
                        kept.append(item)
                        test_height += item_h
                    else:
                        rest.append(item)
                if kept:
                    fitting[col_idx].append({'category': cat.get('category', ''), 'items': kept})
                    used_heights[col_idx] = test_height + 8
                if rest:
                    overflow.append({'category': f"{cat.get('category', '')} (suite)", 'items': rest})
            else:
                overflow.append(cat)
        return fitting, overflow

    def draw_skill_column(self, cats, x, y, w):
        for cat in cats:
            y = self.para_html_at(self.skill_line_html(cat), x, y, w, self.skill_inline)
            y += 3
        return y

    def render_skill_overflow(self, overflow):
        if not overflow:
            return
        self.new_page(False, self.current_name)
        y = self.section_at('Compétences techniques (suite)', self.left, self.y, self.fw, 13.2)
        self.flow(self.left, y + 2, self.fw)
        for cat in overflow:
            self.drawp(self.skill_line_html(cat), self.skill_inline)
            self.y += 3

    def render(self, data):
        self.current_name = data['name']
        self.new_page(first=True, name=data['name'])
        self.text(data['name'], 59.5, 94, 'Poppins-Bold', 32, BLACK)
        title_p = Paragraph(html(data.get('title', '')), ParagraphStyle('head', fontName='Poppins', fontSize=12.2, leading=16, textColor=BLACK))
        title_p.wrap(325, 90)
        title_p.drawOn(self.c, 59.5, H - 118 - 48)
        self._track_page_text(data.get('title', ''))
        sep = 414
        self.line(sep, 140, sep, 807, BLACK, .65)

        # Right column: "Formation & Diplômes" sidebar.
        # Regroups Formations (academic diplomas), Certifications and Spoken Languages
        # into a single client-facing column on the right of the first page.
        rx, rw, y = SIDEBAR_X, SIDEBAR_WIDTH, 211.4
        # The two-line header uses a slightly smaller size than the original 15pt to keep
        # the spaced "FORMATION &" label within the readable column width (right=571.28).
        self.text(spaced('Formation &'), 436.7, y, 'Poppins-SemiBold', 13, TITLE)
        self.text(spaced('Diplômes'), 452.3, y + 20.2, 'Poppins-SemiBold', 15, TITLE)
        self.line(436.7, y + 45, 562, y + 45, TITLE, .55)
        kept, self.sidebar_overflow = self.plan_sidebar(data, SIDEBAR_TOP, self.content_bottom - SIDEBAR_BOTTOM_MARGIN)
        y = SIDEBAR_TOP
        for group in kept:
            y = self.draw_sidebar_group(group, rx, y, rw)

        # Optional profile/description block between the headline title and skills.
        lx, lw = 59.5, 328
        skill_top = 184.6
        desc = data.get('description')
        if desc:
            # Keep the description below the job title with enough breathing room, then push skills down.
            skill_top = self.section_at('Description', lx, 188.0, lw, 11.2)
            skill_top = self.para_at(desc, lx, skill_top - 2.0, lw, self.desc) + (26 if self.compact else 35)

        # Skills
        sx1, sx2 = lx, lx + 174
        sw1, sw2 = 156, 152
        y1 = y2 = skill_top + 25
        skills = prepare_readable_skill_categories(
            data.get('skills', []),
            max_item_chars=int(self.layout_options.get('max_skill_item_chars', DEFAULT_MAX_SKILL_ITEM_CHARS)),
            max_items_per_block=int(self.layout_options.get('max_skill_items_per_block', DEFAULT_MAX_SKILL_ITEMS_PER_BLOCK)),
            max_block_chars=int(self.layout_options.get('max_skill_block_chars', DEFAULT_MAX_SKILL_BLOCK_CHARS)),
        )
        has_skills = any(cat.get('items') for cat in skills if isinstance(cat, dict))
        if has_skills:
            self.section_at('Compétences techniques', lx, skill_top, lw, 14)
            fitted_skills, skill_overflow = self.split_skill_columns_for_page(skills, y1, self.content_bottom - 12)
            y1 = self.draw_skill_column(fitted_skills[0], sx1, y1, sw1)
            y2 = self.draw_skill_column(fitted_skills[1], sx2, y2, sw2)
            exp_y = max(y1, y2) + (14 if self.compact else 20)
        else:
            # Nothing left once the skills are cleaned (lot 2): no empty
            # "Compétences techniques" title, the experiences start here.
            skill_overflow = []
            exp_y = skill_top
        if skill_overflow:
            self.render_skill_overflow(skill_overflow)
            exp_y = self.y + 18
            exp_x, exp_w = self.left, self.right - self.left
        else:
            exp_x, exp_w = lx, lw
        exps = data.get('experiences', [])
        # The experiences title stays with the opener of the first experience:
        # both start here when date, role and the first lines fit below.
        self.flow(exp_x, exp_y + 31, exp_w)
        starts_here = not exps or self.experience_opener_fits(exps[0])
        if (self.force_experiences_new_page and self.page == 1) or exp_y + 45 > self.content_bottom or not starts_here:
            self.new_page(False, self.current_name)
            exp_x, exp_w, exp_y = self.left, self.right - self.left, self.y
        self.section_at('Expériences professionnelles', exp_x, exp_y, exp_w, 13.6)
        self.flow(exp_x, exp_y + 31, exp_w)
        self._mark_flow_bottom(exp_y + 6)
        self.experiences_start_page = self.page

        for idx, exp in enumerate(exps):
            self.render_experience(exp, index=idx, total=len(exps))
        self.render_projects(data.get('projects') or [])
        self.render_sidebar_overflow(self.sidebar_overflow)
        self.c.save()

    def render_projects(self, projects):
        """"Projets & réalisations" (projects outside any experience), after the
        experiences, in the experiences' style: optional date in purple, name in
        bold, details as bullets. Projects without name or date are grouped in
        one bullet list."""
        named, loose = [], []
        for project in projects or []:
            if not isinstance(project, dict):
                continue
            details = [str(d).strip() for d in project.get('details') or [] if str(d).strip()]
            name = str(project.get('name') or '').strip()
            date = str(project.get('date') or '').strip()
            if name or date:
                named.append({'date': date, 'role': name, 'company_highlight': '',
                              'sections': [{'heading': '', 'content': details}] if details else []})
            else:
                loose.extend(details)
        blocks = list(named)
        if loose:
            blocks.append({'date': '', 'role': '', 'company_highlight': '', 'sections': [{'heading': '', 'content': loose}]})
        if not blocks:
            return
        title_h = 31
        if not self._at_page_top():
            room = self._flow_bottom() - self.y - SECTION_TITLE_LEAD - title_h
            lines, total = self.experience_lines_here(blocks[0], room)
            if room <= 0 or lines < min(self.min_experience_opener_lines, total):
                self._continue_on_new_page()
            else:
                self.y += SECTION_TITLE_LEAD
        self.section_at('Projets & réalisations', self.fx, self.y, self.fw, 13.6)
        self._mark_flow_bottom(self.y + 6)
        self.y += title_h
        for index, block in enumerate(blocks):
            if index and not self.experience_opener_fits(block) and not self._at_page_top():
                self._continue_on_new_page()
            if block['date']:
                self.drawp(html(block['date']), self.date)
            if block['role']:
                self.drawp(html(block['role']), self.role)
            for sec in block['sections']:
                self.render_section(sec)
            self.y += self.experience_gap

    # ------------------------------------------------------------ sidebar

    def sidebar_groups(self, data):
        """Groups of the "Formation & Diplômes" column, in drawing order:
        one per formation, then Certifications, then Langues. Each group is
        {'kind', 'lines': [(text, style, gap_after)], 'gap_before', 'gap_after'}."""
        rdate = ParagraphStyle('rdate', parent=self.side_b, textColor=PURPLE)
        rsub = ParagraphStyle('rsub', parent=self.side_b, textColor=PURPLE)
        groups = []
        for f in data.get('formations') or []:
            if not isinstance(f, dict):
                continue
            lines = [(str(f.get(key) or '').strip(), style, 0.0)
                     for key, style in (('date', rdate), ('degree', self.side_b), ('school', self.side))]
            lines = [line for line in lines if line[0]]
            if lines:
                groups.append({'kind': 'formation', 'item': f, 'lines': lines, 'gap_before': 0.0, 'gap_after': 12.0})
        certs = []
        for cert in data.get('certifications') or []:
            text = str(cert.get('name') or '').strip() if isinstance(cert, dict) else str(cert).strip()
            if text:
                certs.append(text)
        if certs:
            lines = [('Certifications', rsub, 0.0)] + [('• ' + text, self.side, 1.0) for text in certs]
            groups.append({'kind': 'certifications', 'items': certs, 'lines': lines, 'gap_before': 6.0, 'gap_after': 8.0})
        langs = []
        for lang in data.get('languages') or []:
            if isinstance(lang, dict):
                name = str(lang.get('name') or '').strip()
                level = str(lang.get('level') or '').strip()
            else:
                name, level = str(lang).strip(), ''
            if name:
                langs.append(f"{name} — {level}" if level else name)
        if langs:
            lines = [('Langues', rsub, 0.0)] + [('• ' + text, self.side, 1.0) for text in langs]
            groups.append({'kind': 'languages', 'items': langs, 'lines': lines, 'gap_before': 6.0, 'gap_after': 4.0})
        return groups

    def sidebar_group_height(self, group, width=SIDEBAR_WIDTH):
        height = group['gap_before'] + group['gap_after']
        for text, style, gap in group['lines']:
            height += self.measure_text(text, style, width) + gap
        return height

    def plan_sidebar(self, data, top, bottom):
        """(groups drawn in the column, groups continued after the experiences).

        Lot 3 (2026-11): the column used to be drawn from a fixed y without
        any bottom check, so long lists ran off the page (12 certifications
        invisible). Everything fits: drawn as before. Otherwise the column
        keeps the formations that fit, then the languages (short, read
        first), then the certifications when the whole list fits; what does
        not fit is drawn full width at the end of the CV, never cut."""
        groups = self.sidebar_groups(data)
        room = bottom - top
        if sum(self.sidebar_group_height(g) for g in groups) <= room:
            return groups, []
        kept, overflow, used = [], [], 0.0
        formations = [g for g in groups if g['kind'] == 'formation']
        others = [g for g in groups if g['kind'] == 'languages'] + [g for g in groups if g['kind'] == 'certifications']
        for group in formations:
            height = self.sidebar_group_height(group)
            if not overflow and used + height <= room:
                kept.append(group)
                used += height
            else:
                overflow.append(group)
        for group in others:
            height = self.sidebar_group_height(group)
            if used + height <= room:
                kept.append(group)
                used += height
            else:
                overflow.append(group)
        return kept, overflow

    def draw_sidebar_group(self, group, x, y, w):
        y += group['gap_before']
        for text, style, gap in group['lines']:
            y = self.para_at(text, x, y, w, style) + gap
        return y + group['gap_after']

    def render_sidebar_overflow(self, overflow):
        """Formations, certifications or languages that did not fit in the
        page-1 column, full width after the experiences and projects."""
        if not overflow:
            return
        formations = [g['item'] for g in overflow if g['kind'] == 'formation']
        blocks = []
        if formations:
            entries = []
            for f in formations:
                degree, school = str(f.get('degree') or '').strip(), str(f.get('school') or '').strip()
                line = ' — '.join(part for part in (
                    f'<font name="Poppins-Bold">{html(degree)}</font>' if degree else '', html(school) if school else '',
                ) if part)
                entries.append({'date': str(f.get('date') or '').strip(), 'role': '', 'line_html': line,
                                'company_highlight': '', 'sections': []})
            blocks.append(('Formation & Diplômes', entries))
        for group in overflow:
            if group['kind'] in ('certifications', 'languages'):
                title = 'Certifications' if group['kind'] == 'certifications' else 'Langues'
                blocks.append((title, [{'date': '', 'role': '', 'company_highlight': '',
                                        'sections': [{'heading': '', 'content': list(group['items'])}]}]))
        for title, entries in blocks:
            title_h = 31
            if not self._at_page_top():
                room = self._flow_bottom() - self.y - SECTION_TITLE_LEAD - title_h
                lines, total = self.experience_lines_here(entries[0], room)
                needs_body = min(self.min_lines_under_heading, max(total, 1))
                if room <= 0 or (total and lines < needs_body) or (not total and room < 2 * self.role.leading):
                    self._continue_on_new_page()
                else:
                    self.y += SECTION_TITLE_LEAD
            self.section_at(title, self.fx, self.y, self.fw, 13.6)
            self._mark_flow_bottom(self.y + 6)
            self.y += title_h
            for index, entry in enumerate(entries):
                if index and not self.experience_opener_fits(entry) and not self._at_page_top():
                    self._continue_on_new_page()
                if entry['date']:
                    self.drawp(html(entry['date']), self.date)
                if entry['role']:
                    self.drawp(html(entry['role']), self.role)
                if entry.get('line_html'):
                    self.drawp(entry['line_html'], self.body)
                    self.y += 4
                for sec in entry['sections']:
                    self.render_section(sec)
            self.y += self.experience_gap

    def role_html(self, exp):
        role = exp.get('role', '')
        company = exp.get('company_highlight')
        if company and company in role:
            role = escape(role).replace(escape(company), purple(company))
            return role
        if company:
            return f'{html(role)} — {purple(company)}'
        return html(role)

    def _sections(self, exp):
        return [sec for sec in exp.get('sections', []) or [] if isinstance(sec, dict)]

    def _opener_heights(self, exp, width=None):
        return (
            self.measure_text(exp.get('date', ''), self.date, width),
            self.measurep(self.role_html(exp), self.role, width),
        )

    def experience_lines_here(self, exp, avail, width=None):
        """(body lines of `exp` that would land in `avail` points, total body
        lines), following the same rules as render_section."""
        date_h, role_h = self._opener_heights(exp, width)
        used = date_h + role_h
        total = sum(self._section_lines(sec, width) for sec in self._sections(exp))
        if used > avail:
            return 0, total
        lines = 0
        for sec in self._sections(exp):
            heading = sec.get('heading')
            _, paras = self._section_paragraphs(sec)
            if not paras:
                used += self.measure_text(heading, self.sub, width) if heading else 0
                continue
            placement = self._place_section_here(heading, paras, avail - used, width)
            if placement is None:
                break
            full, partial, placed, sec_total = placement
            lines += placed
            if placed < sec_total:
                break
            used += (self.measure_text(heading, self.sub, width) if heading else 0) + sum(
                self._lines_of(text, st, width) * st.leading + st.spaceAfter for text, st in paras
            )
            if lines >= self.min_experience_opener_lines:
                break
        return lines, total

    def experience_opener_fits(self, exp) -> bool:
        """Date, role and the first body lines (min_experience_opener_lines, or
        the whole experience when shorter) fit in the room left on the page."""
        lines, total = self.experience_lines_here(exp, self._flow_bottom() - self.y)
        date_h, role_h = self._opener_heights(exp)
        if self.y + date_h + role_h > self._flow_bottom():
            return False
        return lines >= min(self.min_experience_opener_lines, total)

    def estimate_experience_opener_height(self, exp):
        """Height of date + role + the first body lines kept with them."""
        date_h, role_h = self._opener_heights(exp)
        height = date_h + role_h
        needed = self.min_experience_opener_lines
        for sec in self._sections(exp):
            heading = sec.get('heading')
            if heading:
                height += self.measure_text(heading, self.sub)
            _, paras = self._section_paragraphs(sec)
            for text, style in paras:
                n = self._lines_of(text, style)
                take = min(n, needed)
                height += take * style.leading + style.spaceAfter
                needed -= take
                if needed <= 0:
                    return height
        return height

    def _forced_break_would_create_sparse_page(self, opener_height):
        """An explicit break request is skipped on a page still less than half
        full when the experience opener fits: honouring it would leave a
        half-empty page."""
        if not self.allow_grouping:
            return False
        page_half = self.page_start_y + (self._flow_bottom() - self.page_start_y) / 2
        return self.y < page_half and self._flow_bottom() - self.y >= opener_height + self.body.leading * 2

    def maybe_break_before_experience(self, exp, index=0, total=0):
        """Start a new page before `exp` only when its opener does not fit
        (or on an explicit break request). Returns True when a page was added."""
        if self._at_page_top():
            return False
        if index in self.force_page_break_before_experience_indexes and self.y > self.page_start_y + 28:
            if not self._forced_break_would_create_sparse_page(self.estimate_experience_opener_height(exp)):
                self._continue_on_new_page()
                return True
        if self.experience_opener_fits(exp):
            return False
        self._continue_on_new_page()
        return True

    def render_experience(self, exp, index=0, total=0):
        self.maybe_break_before_experience(exp, index=index, total=total)
        self.drawp(html(exp.get('date', '')), self.date)
        self.drawp(self.role_html(exp), self.role)
        for position, sec in enumerate(exp.get('sections', []) or []):
            if isinstance(sec, dict):
                self.render_section(sec, opens_experience=position == 0)
        self.y += self.experience_gap

    def tail_balance_candidates(self, step: float = 20.0) -> list[dict[int, float]]:
        """Flow limits to try for the next-to-last page when the last page
        would hold a few lines only, smallest move first, up to what brings
        the last page to LAST_PAGE_TARGET_FILL; the previous page never goes
        under PENULTIMATE_MIN_FILL."""
        last = self.page
        if last < 2 or self._page_fill(last) >= LAST_PAGE_MIN_FILL:
            return []
        previous = last - 1
        previous_bottom = self.page_flow_bottoms.get(previous)
        if previous_bottom is None:
            return []
        zone = self.content_bottom - FILL_ZONE_TOP
        min_fill = FIRST_PAGE_MIN_FILL_WHEN_BALANCING if previous == 1 else PENULTIMATE_MIN_FILL
        floor = FILL_ZONE_TOP + min_fill * zone
        move = step
        max_move = (LAST_PAGE_TARGET_FILL - self._page_fill(last)) * zone + 4 * self.body.leading
        limits = []
        while move <= max_move:
            limit = previous_bottom - move
            if limit < floor:
                break
            limits.append({previous: limit})
            move += step
        return limits


def plan_section_break(line_counts, leading, space_after, avail, *, min_split=MIN_SPLIT_LINES, min_continuation=MIN_CONTINUATION_LINES):
    """Choose where a section stops on the current page.

    line_counts: lines of each paragraph (bullet) of the section, in order.
    Returns (full, partial, placed): `full` paragraphs drawn whole, then
    `partial` first lines of the next one, `placed` lines in all. The largest
    legal amount wins: a split paragraph keeps `min_split` lines on each side
    and what goes to the next page holds at least `min_continuation` lines.
    (0, 0, 0) when nothing can stay here.
    """
    total = sum(line_counts)
    best = (0, 0, 0)
    used = 0.0
    placed = 0
    for index, count in enumerate(line_counts):
        for k in range(count - min_split, min_split - 1, -1):
            if used + k * leading + space_after > avail + 0.01:
                continue
            if total - placed - k < min_continuation:
                continue
            if placed + k > best[2]:
                best = (index, k, placed + k)
            break
        used += count * leading + space_after
        placed += count
        if used > avail + 0.01:
            break
        rest = total - placed
        if (rest == 0 or rest >= min_continuation) and placed > best[2]:
            best = (index + 1, 0, placed)
    return best


def render_document(out, data, layout_options=None):
    """Render `data` to `out`. When the last page would only hold a short
    tail, render again with the previous page shortened step by step. A
    version is acceptable when it keeps the page count and the page where the
    experiences start, and leaves the previous page above its minimum fill
    (FIRST_PAGE_MIN_FILL_WHEN_BALANCING for page 1); the first one (smallest move) whose last page reaches
    LAST_PAGE_MIN_FILL wins, else the acceptable one with the fullest last
    page if it gains at least 10 points. Otherwise the plain rendering stays."""
    import io

    first_buffer = io.BytesIO()
    first = Renderer(first_buffer, layout_options)
    first.render(data)
    plain_fill = first._page_fill(first.page)
    chosen, best_fill = first_buffer, plain_fill
    for limits in first.tail_balance_candidates():
        buffer = io.BytesIO()
        candidate = Renderer(buffer, layout_options, page_flow_limits=limits)
        candidate.render(data)
        if candidate.page != first.page:
            break
        if getattr(candidate, 'experiences_start_page', 0) != getattr(first, 'experiences_start_page', 0):
            break
        previous = candidate.page - 1
        min_previous_fill = FIRST_PAGE_MIN_FILL_WHEN_BALANCING if previous == 1 else PENULTIMATE_MIN_FILL
        if candidate._page_fill(previous) < min_previous_fill:
            # The break fell much higher than the limit (a whole block moved):
            # the previous page would be left half empty.
            continue
        fill = candidate._page_fill(candidate.page)
        if fill >= LAST_PAGE_MIN_FILL:
            chosen = buffer
            break
        if fill >= plain_fill + 0.10 and fill > best_fill:
            chosen, best_fill = buffer, fill
    Path(out).write_bytes(chosen.getvalue())


def main():
    if len(sys.argv) != 3:
        die('Usage: whub_cv_renderer.py input.json output.pdf')
    inp, out = sys.argv[1], sys.argv[2]
    data = json.loads(Path(inp).read_text(encoding='utf-8'))
    if has_contact(data):
        die('Input JSON appears to contain direct candidate contact info. Remove phone/email/linkedin before rendering.')
    if has_forbidden_identity(data, data.get('_forbidden_identity_terms') if isinstance(data, dict) else None):
        die('Input JSON appears to expose a candidate full name or forbidden identity term. Use first name only.')
    prep_assets()
    register_fonts(ensure_poppins())
    render_document(out, data, data.get('_layout') if isinstance(data.get('_layout'), dict) else None)
    print(out)


if __name__ == '__main__':
    main()
