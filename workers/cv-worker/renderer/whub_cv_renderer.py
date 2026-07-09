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
DEFAULT_MAX_SKILL_ITEMS_PER_BLOCK = 8
DEFAULT_MAX_SKILL_BLOCK_CHARS = 470


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
    def __init__(self, out: str, layout_options: dict | None = None):
        self.c = canvas.Canvas(out, pagesize=A4, initialFontName='Poppins', initialFontSize=8)
        self.page = 0
        self.layout_options = layout_options or {}
        self.anti_crowding = bool(self.layout_options.get('anti_crowding'))
        self.force_experiences_new_page = bool(self.layout_options.get('force_experiences_new_page'))
        self.force_page_break_before_experience_indexes = set(
            int(i) for i in self.layout_options.get('force_page_break_before_experience_indexes', [])
            if str(i).lstrip('-').isdigit()
        )
        self.page_dense_char_threshold = int(self.layout_options.get('page_dense_char_threshold', 3000))
        self.max_used_ratio = float(self.layout_options.get('max_used_ratio', 0.82))
        self.readability_reserve = float(self.layout_options.get('readability_reserve', 155))
        self.allow_grouping = bool(self.layout_options.get('allow_grouping', True))
        self.min_experience_opener_bullets = int(self.layout_options.get('min_experience_opener_bullets', 2))
        self.current_page_chars = 0
        self.page_start_y = 55
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

    def image_top(self, path: Path, x: float, y: float, w: float, h: float) -> None:
        self.c.drawImage(str(path), x, H - y - h, width=w, height=h, mask='auto', preserveAspectRatio=True)

    def brand(self, first=False):
        self.image_top(LOGO, 424, 43, 121, 45)
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
        p = Paragraph(html(s), style)
        _, h = p.wrap(w, 10000)
        p.drawOn(self.c, x, H - y - h)
        return y + h + style.spaceAfter

    def para_html_at(self, html_text, x, y, w, style):
        p = Paragraph(html_text, style)
        _, h = p.wrap(w, 10000)
        p.drawOn(self.c, x, H - y - h)
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
        if self.y + height > self.content_bottom:
            self.new_page(False, name or self.current_name)
            self.flow(self.left, self.y, self.right - self.left)
            return True
        return False

    def _track_page_text(self, text) -> None:
        plain = re.sub(r'<[^>]+>', ' ', str(text))
        plain = re.sub(r'\s+', ' ', plain).strip()
        self.current_page_chars += len(plain)

    def _current_used_ratio(self) -> float:
        return max(0.0, self.y - self.page_start_y) / H

    def _current_page_is_sparse(self) -> bool:
        return (
            self.y > self.page_start_y + 28
            and self._current_used_ratio() <= 0.42
            and self.current_page_chars <= 1200
        )

    def drawp(self, html_text, style):
        """Draw a paragraph in the current flow, splitting across pages if needed."""
        page_changed = False
        remaining_html = html_text
        while True:
            p = Paragraph(remaining_html, style)
            _, h = p.wrap(self.fw, 10000)
            avail = self.content_bottom - self.y
            if h <= avail:
                p.drawOn(self.c, self.fx, H - self.y - h)
                self._track_page_text(p.getPlainText() if hasattr(p, 'getPlainText') else remaining_html)
                self.y += h + style.spaceAfter
                return page_changed

            if avail <= style.leading * 1.5:
                self.new_page(False, self.current_name)
                self.flow(self.left, self.y, self.right - self.left)
                page_changed = True
                continue

            pieces = p.split(self.fw, avail)
            if not pieces:
                self.new_page(False, self.current_name)
                self.flow(self.left, self.y, self.right - self.left)
                page_changed = True
                continue

            first_piece = pieces[0]
            _, ph = first_piece.wrap(self.fw, avail)
            first_piece.drawOn(self.c, self.fx, H - self.y - ph)
            self._track_page_text(first_piece.getPlainText() if hasattr(first_piece, 'getPlainText') else remaining_html)
            self.y += ph + style.spaceAfter
            self.new_page(False, self.current_name)
            self.flow(self.left, self.y, self.right - self.left)
            page_changed = True

            if len(pieces) == 1:
                return page_changed
            remaining = pieces[1]
            remaining_html = html(remaining.getPlainText()) if hasattr(remaining, 'getPlainText') else str(remaining)

    def p(self, s):
        self.drawp(html(s), self.body)

    def bullet(self, s):
        self.drawp('• ' + html(s), self.bul)

    def subhead(self, s):
        return self.drawp(html(s), self.sub)

    def draw_heading_with_min_content(self, heading, content_height, *, keep_full_first_block=False):
        min_body_height = content_height if keep_full_first_block else min(content_height, self.sub.leading * 2)
        needed = self.measure_text(heading, self.sub) + min_body_height
        self.ensure_space(needed)
        return self.subhead(heading)

    def render_bullet_list(self, heading, items):
        if not items:
            return
        first_h = self.measure_text('• ' + str(items[0]), self.bul)
        if heading:
            # Keep a section heading with its first bullet. Previously only two
            # leading units were reserved, so long first bullets could force a
            # page break immediately after the heading and create an orphaned
            # "Heading" / "Heading (suite)" split.
            self.draw_heading_with_min_content(heading, first_h, keep_full_first_block=True)
        for item in items:
            item_h = self.measure_text('• ' + str(item), self.bul)
            if (
                self.anti_crowding
                and self.current_page_chars >= self.page_dense_char_threshold
                and self.y > self.page_start_y + 80
            ):
                self.new_page(False, self.current_name)
                self.flow(self.left, self.y, self.right - self.left)
                if heading:
                    self.subhead(f'{heading} (suite)')
            if heading and self.y + min(item_h, self.bul.leading * 2) > self.content_bottom:
                self.new_page(False, self.current_name)
                self.flow(self.left, self.y, self.right - self.left)
                self.subhead(f'{heading} (suite)')
            self.bullet(item)

    def render_text_section(self, heading, content):
        content_h = self.measure_text(str(content), self.body)
        if heading:
            self.draw_heading_with_min_content(heading, content_h)
        if content:
            self.p(content)

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
        sep = 414
        self.line(sep, 140, sep, 807, BLACK, .65)

        # Right column: "Formation & Diplômes" sidebar.
        # Regroups Formations (academic diplomas), Certifications and Spoken Languages
        # into a single client-facing column on the right of the first page.
        rx, rw, y = 431.6, 138, 211.4
        # The two-line header uses a slightly smaller size than the original 15pt to keep
        # the spaced "FORMATION &" label within the readable column width (right=571.28).
        self.text(spaced('Formation &'), 436.7, y, 'Poppins-SemiBold', 13, TITLE)
        self.text(spaced('Diplômes'), 452.3, y + 20.2, 'Poppins-SemiBold', 15, TITLE)
        self.line(436.7, y + 45, 562, y + 45, TITLE, .55)
        y = 270
        formations = data.get('formations') or []
        for f in formations:
            y = self.para_at(f.get('date', ''), rx, y, rw, ParagraphStyle('rdate', parent=self.side_b, textColor=PURPLE))
            y = self.para_at(f.get('degree', ''), rx, y, rw, self.side_b)
            y = self.para_at(f.get('school', ''), rx, y, rw, self.side)
            y += 12

        # Certifications sub-section: only when the LLM/source actually surfaced some.
        certifications = data.get('certifications') or []
        if certifications:
            y += 6
            y = self.para_at('Certifications', rx, y, rw, ParagraphStyle('rsub', parent=self.side_b, textColor=PURPLE))
            for cert in certifications:
                cert_text = str(cert).strip() if not isinstance(cert, dict) else str(cert.get('name') or '').strip()
                if not cert_text:
                    continue
                # Each certification = one short bullet in the sidebar.
                y = self.para_at('• ' + cert_text, rx, y, rw, self.side) + 1
            y += 8

        # Spoken languages sub-section: only the languages the candidate speaks/writes.
        # `languages` is a list of {name, level} dicts; legacy support: list of strings.
        languages = data.get('languages') or []
        if languages:
            y += 6
            y = self.para_at('Langues', rx, y, rw, ParagraphStyle('rsub', parent=self.side_b, textColor=PURPLE))
            for lang in languages:
                if isinstance(lang, dict):
                    name = str(lang.get('name') or '').strip()
                    level = str(lang.get('level') or '').strip()
                else:
                    name = str(lang).strip()
                    level = ''
                if not name:
                    continue
                if level:
                    line = f"• {name} — {level}"
                else:
                    line = f"• {name}"
                y = self.para_at(line, rx, y, rw, self.side) + 1
            y += 4

        # Optional profile/description block between the headline title and skills.
        lx, lw = 59.5, 328
        skill_top = 184.6
        desc = data.get('description')
        if desc:
            # Keep the description below the job title with enough breathing room, then push skills down.
            skill_top = self.section_at('Description', lx, 188.0, lw, 11.2)
            skill_top = self.para_at(desc, lx, skill_top - 2.0, lw, self.desc) + 35

        # Skills
        self.section_at('Compétences techniques', lx, skill_top, lw, 14)
        sx1, sx2 = lx, lx + 174
        sw1, sw2 = 156, 152
        y1 = y2 = skill_top + 25
        skills = prepare_readable_skill_categories(
            data.get('skills', []),
            max_item_chars=int(self.layout_options.get('max_skill_item_chars', DEFAULT_MAX_SKILL_ITEM_CHARS)),
            max_items_per_block=int(self.layout_options.get('max_skill_items_per_block', DEFAULT_MAX_SKILL_ITEMS_PER_BLOCK)),
            max_block_chars=int(self.layout_options.get('max_skill_block_chars', DEFAULT_MAX_SKILL_BLOCK_CHARS)),
        )
        fitted_skills, skill_overflow = self.split_skill_columns_for_page(skills, y1, self.content_bottom - 12)
        y1 = self.draw_skill_column(fitted_skills[0], sx1, y1, sw1)
        y2 = self.draw_skill_column(fitted_skills[1], sx2, y2, sw2)

        exp_y = max(y1, y2) + 20
        if skill_overflow:
            self.render_skill_overflow(skill_overflow)
            exp_y = self.y + 18
            exp_x, exp_w = self.left, self.right - self.left
        else:
            exp_x, exp_w = lx, lw
        overflow_page_lacks_experience_room = bool(skill_overflow) and exp_y > float(
            self.layout_options.get('max_skill_overflow_experience_start_y', 450)
        )
        exps = data.get('experiences', [])
        first_experience_opener_height = self.estimate_experience_opener_height(exps[0]) if exps else 0
        experience_heading_height = self.measure_text('Expériences professionnelles', self.sub) + 31
        first_experience_would_orphan = bool(exps) and (
            exp_y + experience_heading_height + first_experience_opener_height > self.content_bottom
        )
        if self.force_experiences_new_page and self.page == 1:
            self.new_page(False, self.current_name)
            exp_x, exp_w, exp_y = self.left, self.right - self.left, self.y
        elif overflow_page_lacks_experience_room:
            # If the skills overflow already consumes most of the continuation page,
            # do not start a long first experience at the bottom and leave a tiny
            # "(suite)" tail on the next page. A clean full-width experience page is
            # less sparse than a false half-page split.
            self.new_page(False, self.current_name)
            exp_x, exp_w, exp_y = self.left, self.right - self.left, self.y
        elif exp_y + 45 > self.content_bottom or first_experience_would_orphan:
            self.new_page(False, self.current_name)
            exp_x, exp_w, exp_y = self.left, self.right - self.left, self.y
        self.section_at('Expériences professionnelles', exp_x, exp_y, exp_w, 13.6)
        self.flow(exp_x, exp_y + 31, exp_w)

        if exps:
            for idx, exp in enumerate(exps):
                if idx == 1 and self.page == 1 and not self._current_page_is_sparse():
                    # Keep a genuinely loaded page-1 experience area readable by
                    # moving following experiences into the full-width continuation
                    # flow. If page 1 is still sparse, keep grouping enabled so short
                    # / medium faithful CVs do not create a false sparse tail page.
                    self.new_page(False, data['name'])
                    self.flow(self.left, self.y, self.right - self.left)
                self.render_experience(exp, index=idx, total=len(exps))
        self.c.save()

    def role_html(self, exp):
        role = exp.get('role', '')
        company = exp.get('company_highlight')
        if company and company in role:
            role = escape(role).replace(escape(company), purple(company))
            return role
        if company:
            return f'{html(role)} — {purple(company)}'
        return html(role)

    def render_section(self, sec):
        heading = sec.get('heading')
        content = sec.get('content', '')
        if (
            self.anti_crowding
            and self.current_page_chars >= self.page_dense_char_threshold
            and self.y > self.page_start_y + 80
        ):
            self.new_page(False, self.current_name)
            self.flow(self.left, self.y, self.right - self.left)
        if isinstance(content, list):
            self.render_bullet_list(heading, content)
        elif content:
            self.render_text_section(heading, content)
        elif heading:
            self.ensure_space(self.measure_text(heading, self.sub))
            self.subhead(heading)

    def estimate_experience_opener_height(self, exp):
        # Keep each experience opening together: date + role + heading + first
        # source lines. The renderer may split the full section later, but it
        # must not leave a date/title opener or a single first bullet stranded at
        # the bottom of a page.
        opener_height = self.measure_text(exp.get('date', ''), self.date) + self.measurep(self.role_html(exp), self.role) + 24
        sections = exp.get('sections', [])
        if sections:
            first = sections[0]
            content = first.get('content', '')
            if first.get('heading'):
                opener_height += self.measure_text(first.get('heading', ''), self.sub)
            if isinstance(content, list) and content:
                kept_items = content[:max(1, self.min_experience_opener_bullets)]
                for item in kept_items:
                    opener_height += self.measure_text('• ' + str(item), self.bul)
            elif content:
                opener_height += min(self.measure_text(str(content), self.body), self.body.leading * 3)
        return opener_height

    def _forced_break_would_create_sparse_page(self, opener_height):
        if not self.allow_grouping or not self._current_page_is_sparse():
            return False
        remaining = self.content_bottom - self.y
        return remaining >= opener_height + self.body.leading * 2

    def maybe_break_before_experience(self, exp, index=0, total=0):
        opener_height = self.estimate_experience_opener_height(exp)
        if index in self.force_page_break_before_experience_indexes and self.y > self.page_start_y + 28:
            if not self._forced_break_would_create_sparse_page(opener_height):
                self.new_page(False, self.current_name)
                self.flow(self.left, self.y, self.right - self.left)
                return True
            return False
        if not self.anti_crowding or index <= 0:
            return False
        # Non-destructive anti-crowding: move only the next experience opener/body
        # to a fresh page when the current one is already visually loaded.
        if self.y <= self.page_start_y + 28:
            return False
        remaining = self.content_bottom - self.y
        dense_by_text = self.current_page_chars >= self.page_dense_char_threshold
        dense_by_height = self._current_used_ratio() >= self.max_used_ratio
        weak_remaining = remaining < max(self.readability_reserve, opener_height + self.body.leading * 4)
        if dense_by_text or dense_by_height or weak_remaining:
            self.new_page(False, self.current_name)
            self.flow(self.left, self.y, self.right - self.left)
            return True
        return False

    def render_experience(self, exp, index=0, total=0):
        self.maybe_break_before_experience(exp, index=index, total=total)
        opener_height = self.estimate_experience_opener_height(exp)
        if self.y + opener_height > H - self.bottom:
            self.new_page(False, self.current_name)
            self.flow(self.left, self.y, self.right - self.left)
        self.drawp(html(exp.get('date', '')), self.date)
        self.drawp(self.role_html(exp), self.role)
        for sec in exp.get('sections', []):
            self.render_section(sec)
        self.y += 13


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
    Renderer(out, data.get('_layout') if isinstance(data.get('_layout'), dict) else None).render(data)
    print(out)


if __name__ == '__main__':
    main()
