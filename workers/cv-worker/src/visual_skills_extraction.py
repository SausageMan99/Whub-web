from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
import re
import unicodedata

import fitz


@dataclass(frozen=True)
class VisualSkillsResult:
    skills: list[dict]
    confidence: float
    warnings: list[str] = field(default_factory=list)
    source: str = "visual_pdf_blocks"


@dataclass(frozen=True)
class _VisualBlock:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


_FOOTER_RE = re.compile(
    r"^(?:cv\s+cr[ée]é\s+sur|\d+\s*/\s*\d+|\d+\s*/\s*\d+\s+cv\s+cr[ée]é\s+sur)$",
    re.IGNORECASE,
)

_KNOWN_SKILL_HEADINGS = {
    "competences fonctionnelles": "Compétences fonctionnelles",
    "methodologie de travail": "Méthodologie de travail",
    "mainframe": "Mainframe",
    "web .net": "Web .NET",
    "testeur fonctionnel": "Testeur fonctionnel",
    "base de donnees": "Base De Données",
    "competences organisationnelles": "Compétences Organisationnelles",
    "java": "Java",
    # Omar-style clean source category labels.
    "plateformes": "Technologies Plateformes",
    "technologies plateformes": "Technologies Plateformes",
    "front-end": "Front-end",
    "frontend": "Front-end",
    "data": "Data",
    "ops": "Ops",
    "methodologies": "Méthodologies",
    "reseau & securite": "Réseau & Sécurité",
    "qualite & analyse": "Qualité & Analyse",
    "messaging": "Messaging",
    "divers": "Divers",
}

_SKILL_SECTION_ANCHORS = {
    "competences",
    "domaines de competences",
    "synthese des competences",
    "technologies",
}

_STOP_HEADINGS = {
    "formations",
    "formation",
    "diplomes",
    "diplomes et formations",
    "langues",
    "certifications",
    "titres / certifications",
    "experiences professionnelles",
    "experience professionnelle",
}

_EXPERIENCE_SENTENCE_HINTS = (
    "maintenance applicative",
    "analyse et redaction",
    "chiffrage des demandes",
    "mise en place et suivi",
    "developpement des batchs",
    "developpement des composants",
    "livraisons des programmes",
    "realisation des plans de tests",
    "correction et suivi",
    "environnement technique",
    "projet :",
)


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", without_marks.casefold()).strip(" :;•-–—")


def _is_footer_text(text: str) -> bool:
    return bool(_FOOTER_RE.match(_normalize_ws(text)))


def _canonical_skill_heading(text: str) -> str | None:
    return _KNOWN_SKILL_HEADINGS.get(_fold(text))


def _is_skill_section_heading(text: str) -> bool:
    return _canonical_skill_heading(text) is not None


def _looks_like_experience_sentence(text: str) -> bool:
    normalized = _normalize_ws(text)
    folded = _fold(normalized)
    if len(normalized) > 120:
        return True
    if normalized.endswith(".") and len(normalized) > 45:
        return True
    return any(hint in folded for hint in _EXPERIENCE_SENTENCE_HINTS)


def _extract_blocks(pdf_path: Path) -> list[_VisualBlock]:
    doc = fitz.open(str(pdf_path))
    blocks: list[_VisualBlock] = []
    for page_index, page in enumerate(doc):
        for raw in page.get_text("blocks"):
            if len(raw) < 5:
                continue
            x0, y0, x1, y1, text = raw[:5]
            cleaned = str(text or "").strip()
            if cleaned and not _is_footer_text(cleaned):
                blocks.append(_VisualBlock(page_index, float(x0), float(y0), float(x1), float(y1), cleaned))
    return sorted(blocks, key=lambda block: (block.page, round(block.y0, 1), round(block.x0, 1)))


def _split_block_lines(text: str) -> list[str]:
    raw_lines = str(text or "").replace("\r", "\n").split("\n")
    lines: list[str] = []
    for raw in raw_lines:
        line = _normalize_ws(raw).strip(" •")
        if line and not _is_footer_text(line):
            lines.append(line)
    return lines


def _append_atomic_item(grouped: dict[str, list[str]], category: str, item: str) -> None:
    cleaned = _normalize_ws(item).strip(" ,;:•")
    if not cleaned or _is_footer_text(cleaned) or _looks_like_experience_sentence(cleaned):
        return
    grouped.setdefault(category, [])
    if cleaned not in grouped[category]:
        grouped[category].append(cleaned)


def _split_top_level_commas(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in str(text or ""):
        if ch == "(":
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
        if ch == "," and depth == 0:
            part = _normalize_ws("".join(buf)).strip(" ,;:•")
            if part:
                parts.append(part)
            buf = []
            continue
        buf.append(ch)
    tail = _normalize_ws("".join(buf)).strip(" ,;:•")
    if tail:
        parts.append(tail)
    return parts


def _split_skill_items(line: str) -> list[str]:
    cleaned = _normalize_ws(line).strip(" ,;:•")
    if not cleaned:
        return []
    if "," not in cleaned:
        return [cleaned]
    parts = _split_top_level_commas(cleaned)
    if len(parts) <= 1:
        return [cleaned]
    return parts


def _append_item(grouped: dict[str, list[str]], category: str, item: str) -> None:
    for part in _split_skill_items(item):
        _append_atomic_item(grouped, category, part)


def _score_confidence(skills: list[dict], start_seen: bool, warnings: list[str]) -> float:
    if not start_seen:
        warnings.append("skills_heading_not_found")
        return 0.0
    total_items = sum(len(skill.get("items") or []) for skill in skills)
    if len(skills) < 3 or total_items < 8:
        warnings.append("too_few_visual_skills")
        return 0.4
    if any(_is_footer_text(str(item)) for skill in skills for item in skill.get("items", [])):
        warnings.append("footer_leak_detected")
        return 0.5
    if any(len(str(item)) > 120 for skill in skills for item in skill.get("items", [])):
        warnings.append("oversized_skill_item_detected")
        return 0.5
    return 0.9


def _handle_competences_line(line: str) -> str | None:
    """Return an inline subsection heading after COMPÉTENCES, if present."""
    stripped = _normalize_ws(line)
    folded = _fold(stripped)
    if folded == "competences":
        return None
    if not folded.startswith("competences "):
        return None
    remainder = re.sub(r"^comp[ée]tences\b", "", stripped, flags=re.IGNORECASE).strip(" :;-–—")
    return _canonical_skill_heading(remainder)


def extract_visual_skills(pdf_path: Path) -> VisualSkillsResult:
    try:
        blocks = _extract_blocks(pdf_path)
    except Exception:  # noqa: BLE001 - visual skills is an optional source-wins enhancement.
        return VisualSkillsResult(skills=[], confidence=0.0, warnings=["pdf_unreadable"])
    start_seen = False
    current_category: str | None = None
    grouped: dict[str, list[str]] = {}
    warnings: list[str] = []
    stop = False

    for block in blocks:
        if stop:
            break
        for line in _split_block_lines(block.text):
            folded = _fold(line)
            if not start_seen:
                if folded in _SKILL_SECTION_ANCHORS or folded.startswith("competences "):
                    start_seen = True
                    inline_heading = _handle_competences_line(line)
                    if inline_heading:
                        current_category = inline_heading
                        grouped.setdefault(current_category, [])
                continue

            canonical = _canonical_skill_heading(line)
            if canonical:
                current_category = canonical
                grouped.setdefault(current_category, [])
                continue

            if folded in _STOP_HEADINGS:
                stop = True
                break

            if current_category is not None:
                _append_item(grouped, current_category, line)

    skills = [{"category": category, "items": items} for category, items in grouped.items() if items]
    confidence = _score_confidence(skills, start_seen, warnings)
    result = VisualSkillsResult(skills=skills, confidence=confidence, warnings=warnings)
    if result.confidence >= 0.75:
        return result
    styled = _extract_styled_skills(pdf_path)
    return styled if styled.confidence > result.confidence else result


# ---------------------------------------------------------------------------
# Style-aware extraction (Canva-style two-column templates)
# ---------------------------------------------------------------------------
#
# These templates carry their structure in the font styles, not in known words:
# a large section heading ("C O M P É T E N C E S   T E C H N I Q U E S"), bold
# category lines in one or two columns, "•" items whose wrapped lines continue
# below, and a sidebar column (formations) laid out beside the skills. Plain
# text extraction interleaves the columns; reading the styles and positions
# keeps each item whole, under its own source category.


@dataclass(frozen=True)
class _StyledLine:
    page: int
    x0: float
    y0: float
    x1: float
    size: float
    bold: bool
    text: str


_STYLED_SECTION_ANCHORS = {
    "competences",
    "competencestechniques",
    "competencescles",
    "competencesfonctionnelles",
    "domainesdecompetences",
    "savoir-faire",
    "savoirfaire",
    "expertises",
}
_NON_SKILL_CATEGORY_RE = re.compile(
    r"^(?:langues?|competences\s+linguistiques|loisirs|centres?\s+d['’]interets?|hobbies|reseaux\s+sociaux"
    r"|certifications?|formations?|diplomes?|contact|coordonnees)\b"
)
_CONTINUED_CATEGORY_RE = re.compile(r"\s*(?:\(suite\)|[-–—]\s*suite)\s*$", re.IGNORECASE)
_BULLET_PREFIX_RE = re.compile(r"^[•·●▪◦➢✓]\s*")
# "risques. Data & Cloud: AWS": an item that restarts mid-way is a cut sentence.
_SENTENCE_FRAGMENT_RE = re.compile(r"\w\.\s+[A-ZÀ-ÖØ-Þ]")
_LINKING_WORD_RE = re.compile(r"\b(?:et|de|des|du|la|le|les|en|pour|avec|aux?|à|sur|dans)\b", re.IGNORECASE)
_SECTION_HEADING_SIZE_RATIO = 1.3
_STYLED_MIN_CATEGORIES = 2
_STYLED_MIN_ITEMS = 6


def _styled_lines(doc) -> list[_StyledLine]:
    lines: list[_StyledLine] = []
    for page_index, page in enumerate(doc):
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                spans = [span for span in line.get("spans", []) if str(span.get("text") or "").strip()]
                if not spans:
                    continue
                text = _normalize_ws("".join(str(span.get("text") or "") for span in line["spans"]))
                if _is_footer_text(text):
                    continue
                bold = all(
                    (int(span.get("flags") or 0) & 16) or "bold" in str(span.get("font") or "").lower()
                    for span in spans
                )
                x0, y0, x1, _y1 = line["bbox"]
                size = max(float(span.get("size") or 0) for span in spans)
                lines.append(_StyledLine(page_index, float(x0), float(y0), float(x1), size, bool(bold), text))
    return lines


def _styled_heading_key(text: str) -> str:
    return _fold(text).replace(" ", "")


def _same_column(a: _StyledLine, b: _StyledLine) -> bool:
    return abs(a.x0 - b.x0) <= 12


def _follows_closely(previous: _StyledLine, line: _StyledLine) -> bool:
    return 0 < line.y0 - previous.y0 <= max(previous.size, line.size) * 1.8


def _styled_section_lines(lines: list[_StyledLine]) -> tuple[list[_StyledLine], bool]:
    """Lines owned by the skills section heading, column by column, and whether
    another section heading closes it on the same page (else it may go on)."""
    if not lines:
        return [], False
    sizes = sorted(line.size for line in lines)
    body_size = sizes[len(sizes) // 2]

    def is_section_heading(line: _StyledLine) -> bool:
        return line.size >= body_size * _SECTION_HEADING_SIZE_RATIO and len(line.text) <= 60

    anchor = next(
        (line for line in lines if is_section_heading(line) and _styled_heading_key(line.text) in _STYLED_SECTION_ANCHORS),
        None,
    )
    if anchor is None:
        return [], False
    headings = [line for line in lines if line.page == anchor.page and is_section_heading(line)]

    def owner(line: _StyledLine) -> _StyledLine | None:
        # Headings above the line that start at or left of it; the right-most
        # column of them is the line's own (a FORMATIONS sidebar heading owns
        # its column, a short COMPÉTENCES heading still owns the second skills
        # column), then the closest heading above in that column.
        above = [heading for heading in headings if heading.y0 < line.y0 - 1 and heading.x0 <= line.x0 + 8]
        if not above:
            return None
        column_x = max(heading.x0 for heading in above)
        return max((heading for heading in above if column_x - heading.x0 <= 12), key=lambda heading: heading.y0)

    owned = [
        line for line in lines
        if line.page == anchor.page and not is_section_heading(line) and owner(line) is anchor
    ]
    last_y = max((line.y0 for line in owned), default=anchor.y0)
    closed = any(heading.y0 > last_y and abs(heading.x0 - anchor.x0) <= 12 for heading in headings)
    if not closed:
        # The section can also end with its page: the next page then opens with
        # a section heading, after at most the repeated page header (first name).
        next_page = sorted((line for line in lines if line.page == anchor.page + 1), key=lambda line: line.y0)
        first_heading = next((index for index, line in enumerate(next_page) if is_section_heading(line)), None)
        closed = first_heading is not None and first_heading <= 1 and all(len(line.text) <= 40 for line in next_page[:first_heading])
    return sorted(owned, key=lambda line: (round(line.x0 / 12), line.y0)), closed


def _styled_categories(section: list[_StyledLine]) -> tuple[list[tuple[_StyledLine, str, list[tuple[str, bool]]]], int]:
    """Return (heading line, category, [(item, bulleted)]) in reading order, and
    the number of lines found before any category (content without a home)."""
    categories: list[tuple[_StyledLine, str, list[tuple[str, bool]]]] = []
    uncategorised = 0
    previous: _StyledLine | None = None
    previous_was_heading = False
    for line in section:
        bullet = _BULLET_PREFIX_RE.match(line.text)
        contiguous = previous is not None and _same_column(previous, line) and _follows_closely(previous, line)
        if line.bold and not bullet and len(line.text) <= 60:
            if previous_was_heading and contiguous and categories and not categories[-1][2]:
                heading, name, items = categories[-1]
                categories[-1] = (heading, f"{name} {line.text}", items)
            else:
                categories.append((line, line.text, []))
            previous, previous_was_heading = line, True
            continue
        previous_was_heading = False
        if not categories:
            uncategorised += 1
            previous = line
            continue
        items = categories[-1][2]
        if bullet:
            items.append((line.text[bullet.end():].strip(), True))
        elif items and contiguous:
            text, bulleted = items[-1]
            items[-1] = (f"{text} {line.text}".strip(), bulleted)
        else:
            items.append((line.text, False))
        previous = line
    # Reading order of the source: row by row, left to right.
    return sorted(categories, key=lambda entry: (entry[0].page, round(entry[0].y0 / 6), entry[0].x0)), uncategorised


def _is_atomic_skill_list(text: str) -> bool:
    """True for "Python, Java, Next.js, Azure DevOps"; false for phrases such as
    "Planning prévisionnel, plan de charge, budget" or "Tests API : Postman, SoapUI"."""
    if ":" in text:
        return False
    parts = _split_top_level_commas(text)
    # Two parts only when both are single tools: "Django, PyTest", but not
    # "Environnements Microsoft 365, Azure EntraID".
    if len(parts) < 2 or (len(parts) == 2 and any(len(part.split()) > 1 for part in parts)):
        return False
    return all(
        len(part.split()) <= 3 and not part[:1].islower() and not _LINKING_WORD_RE.search(part)
        for part in parts
    )


def _extract_styled_skills(pdf_path: Path) -> VisualSkillsResult:
    try:
        lines = _styled_lines(fitz.open(str(pdf_path)))
    except Exception:  # noqa: BLE001 - optional source-wins enhancement
        return VisualSkillsResult(skills=[], confidence=0.0, warnings=["pdf_unreadable"], source="visual_pdf_styles")
    section, closed = _styled_section_lines(lines)
    if not section:
        return VisualSkillsResult(skills=[], confidence=0.0, warnings=["styled_skills_section_not_found"], source="visual_pdf_styles")

    categories, uncategorised = _styled_categories(section)
    grouped: dict[str, list[str]] = {}
    for _heading, raw_category, raw_items in categories:
        category = _CONTINUED_CATEGORY_RE.sub("", raw_category).strip(" :")
        if not category or _NON_SKILL_CATEGORY_RE.match(_fold(category)):
            continue
        for text, bulleted in raw_items:
            # A bullet is one item as the candidate wrote it, unless it is a
            # plain list of tools; an unbulleted line is such a list.
            text = _normalize_ws(text).strip(" ,;")
            values = _split_skill_items(text) if not bulleted or _is_atomic_skill_list(text) else [text]
            for value in values:
                if value and value not in grouped.setdefault(category, []):
                    grouped[category].append(value)

    skills = [{"category": category, "items": items} for category, items in grouped.items() if items]
    items = [item for skill in skills for item in skill["items"]]
    warnings: list[str] = []
    # The override replaces every model skill, so any doubt about having read
    # the whole section keeps the current skills instead.
    if not closed:
        warnings.append("skills_section_may_continue")
        confidence = 0.5
    elif uncategorised:
        warnings.append("uncategorised_skill_lines")
        confidence = 0.5
    elif len(skills) < _STYLED_MIN_CATEGORIES or len(items) < _STYLED_MIN_ITEMS:
        warnings.append("too_few_visual_skills")
        confidence = 0.4
    elif any(len(item) > 120 for item in items):
        warnings.append("oversized_skill_item_detected")
        confidence = 0.5
    elif any(_SENTENCE_FRAGMENT_RE.search(item) or item[:1].islower() for item in items):
        warnings.append("broken_skill_item_detected")
        confidence = 0.5
    else:
        confidence = 0.9
    return VisualSkillsResult(skills=skills, confidence=confidence, warnings=warnings, source="visual_pdf_styles")


def apply_visual_skills_override(
    structured: dict,
    visual: VisualSkillsResult,
    *,
    min_confidence: float = 0.75,
) -> dict:
    out = deepcopy(structured)
    if visual.confidence < min_confidence or not visual.skills:
        return out
    out["skills"] = deepcopy(visual.skills)
    overrides = out.setdefault("_source_overrides", {})
    overrides["skills"] = {
        "source": visual.source,
        "confidence": visual.confidence,
        "warnings": list(visual.warnings),
    }
    return out
