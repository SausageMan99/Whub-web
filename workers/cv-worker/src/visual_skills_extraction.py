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
    return VisualSkillsResult(skills=skills, confidence=confidence, warnings=warnings)


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
