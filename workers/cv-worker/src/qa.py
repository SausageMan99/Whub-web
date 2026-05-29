from pathlib import Path
from typing import Any, cast
import re
import fitz

from .structuring import (
    extract_experience_location_facts,
    extract_source_business_coverage_facts,
    find_numbered_placeholder_repetitions,
    _contains_fidelity_fact,
    _iter_json_strings,
    _normalize_for_fidelity,
    _role_fact_fragments,
)

CONTACT_PATTERNS = {
    "email": r"@",
    "linkedin": r"linkedin",
    "url": r"https?://|github\.com|\.com\b",
    "phone_fr": r"(?:\+33|\b0[67])(?:[ .-]?\d{2}){4}\b",
}

READABLE_MARGIN_PT = 24
BBOX_TOLERANCE_PT = 1.5
PAGE_DENSE_CHAR_THRESHOLD = 3000
PAGE_DENSE_BLOCK_THRESHOLD = 42
LAST_PAGE_SPARSE_CHAR_THRESHOLD = 180
LAST_PAGE_SPARSE_BLOCK_THRESHOLD = 4
LAST_PAGE_UNDERFILLED_CHAR_THRESHOLD = 650
LAST_PAGE_UNDERFILLED_USED_RATIO = 0.35
EXPERIENCE_ORPHAN_BOTTOM_ZONE_PT = 150
SKILL_DENSE_CHAR_THRESHOLD = 700
SKILL_DENSE_SEPARATOR_THRESHOLD = 18

SKILL_HEADING_RE = re.compile(r"comp[ée]tences|cloud|devops|backend|frontend|outils|m[ée]thodes|data", re.I)
EXPERIENCE_SECTION_RE = re.compile(r"exp[ée]riences?|missions?|prestations?|r[ée]alis[ée]e?s?|activit[ée]s?|environnement", re.I)
EXPERIENCE_DATE_RE = re.compile(r"(?:19|20)\d{2}|aujourd|janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre|d[ée]cembre", re.I)
CONTINUATION_START_RE = re.compile(r"^(?:\(suite\)|missions?\s*\(suite\)|livrables?\s+cl[ée]s?\s*\(suite\))(?:\s|$|[:–—-])", re.I)

SOFT_LAYOUT_CODES = {
    "page_too_dense",
    "last_page_sparse",
    "bad_page_break",
    "skill_block_too_long",
    "skills_too_dense",
    "experience_orphan_heading",
    "experience_section_orphan_heading",
    "skill_overflow_page_created",
    "page_dense_but_acceptable",
    "page_too_sparse",
    "experience_split_mid_block",
    "page_underfilled_with_next_experience_fit",
}


def classify_qa_report(report: dict) -> tuple[str, list[dict[str, Any]]]:
    """Return ('passed'|'draft'|'failed', layout warnings to expose).

    run_qa remains strict: any issue makes passed false and may raise QAError.
    This classifier is the worker boundary deciding whether a strict QA failure
    is safe enough to expose as a downloadable draft.
    """
    hard_failed = (
        bool(report.get("contact_hits"))
        or bool(report.get("bad_glyphs"))
        or bool(report.get("content_integrity_issues"))
        or bool(report.get("text_overflow_hits"))
        or not report.get("has_logo")
        or not report.get("has_watermark")
        or int(report.get("pages") or 0) <= 0
    )
    if hard_failed:
        return "failed", []

    layout_issues = [issue for issue in (report.get("layout_issues") or []) if isinstance(issue, dict)]
    unknown_layout = [issue for issue in layout_issues if issue.get("code") not in SOFT_LAYOUT_CODES]
    if unknown_layout:
        return "failed", []
    if layout_issues:
        return "draft", layout_issues
    return "passed", []


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


def _text_blocks(page: fitz.Page) -> list[dict[str, Any]]:
    return [
        block
        for block in cast(dict[str, Any], page.get_text("dict")).get("blocks", [])
        if block.get("type") == 0 and _block_text(block)
    ]


def _issue(code: str, page: int, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "page": page, "message": message, **extra}


def _uppercase_ratio(text: str) -> float:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for char in letters if char.isupper()) / len(letters)


def _looks_like_experience_heading(text: str) -> bool:
    normalized = " ".join(text.split())
    if not normalized or len(normalized) > 140:
        return False
    if EXPERIENCE_DATE_RE.search(normalized):
        return True
    if _uppercase_ratio(normalized) >= 0.65 and len(normalized) >= 12:
        return True
    return bool(re.search(r"\b(chez|client|architecte|d[ée]veloppeur|consultant|lead|chef de projet|ing[ée]nieur)\b", normalized, re.I))


def _looks_like_skill_heading(text: str) -> bool:
    normalized = " ".join(text.split()).strip(" :-–—•\t")
    if not normalized or len(normalized) > 90:
        return False
    if text.lstrip().startswith(("•", "-")):
        return False
    if EXPERIENCE_SECTION_RE.search(normalized):
        return False
    return bool(SKILL_HEADING_RE.search(normalized))


def _page_text_stats(blocks: list[dict[str, Any]]) -> tuple[str, int, float, float]:
    texts = [_block_text(block) for block in blocks]
    text = "\n".join(texts)
    char_count = sum(len(item) for item in texts)
    y0_values = [float(block["bbox"][1]) for block in blocks]
    y1_values = [float(block["bbox"][3]) for block in blocks]
    used_top = min(y0_values) if y0_values else 0.0
    used_bottom = max(y1_values) if y1_values else 0.0
    return text, char_count, used_top, used_bottom


def collect_page_layout_metrics(doc: fitz.Document) -> list[dict[str, Any]]:
    """Return deterministic page-level layout metrics used by QA heuristics."""
    metrics: list[dict[str, Any]] = []
    for page_index in range(1, doc.page_count + 1):
        page = doc[page_index - 1]
        blocks = sorted(_text_blocks(page), key=lambda block: (block["bbox"][1], block["bbox"][0]))
        text, char_count, used_top, used_bottom = _page_text_stats(blocks)
        block_count = len(blocks)
        page_height = float(page.rect.height or 0.0)
        used_ratio = (used_bottom - used_top) / page_height if page_height else 0.0
        blank_after_pt = max(0.0, page_height - used_bottom) if blocks else page_height
        first_text = " ".join((_block_text(blocks[0]) if blocks else "").split())
        metrics.append({
            "page": page_index,
            "char_count": char_count,
            "block_count": block_count,
            "used_ratio": used_ratio,
            "blank_after_pt": blank_after_pt,
            "starts_with_suite": bool(CONTINUATION_START_RE.search(first_text)),
            "has_experience_heading": any(
                _looks_like_experience_heading(_block_text(block)) or bool(EXPERIENCE_SECTION_RE.search(_block_text(block)))
                for block in blocks
            ),
            # Internal fields reused by legacy layout checks.
            "text": text,
            "used_top": used_top,
            "used_bottom": used_bottom,
            "blocks": blocks,
        })
    return metrics


def find_layout_issues(doc: fitz.Document) -> list[dict[str, Any]]:
    """Detect visually ugly but technically valid CV layouts.

    The checks intentionally emit stable, actionable codes for the worker:
    dense/overflowing skills, orphaned experience openers, bad page breaks,
    sparse final pages, and abnormally dense pages. They are heuristic because
    PDF text extraction has no semantic model, but each finding includes page,
    snippet and metrics so downstream remediation can decide safely.
    """
    findings: list[dict[str, Any]] = []
    page_count = doc.page_count
    page_metrics = collect_page_layout_metrics(doc)
    for metric in page_metrics:
        page_index = int(metric["page"])
        page = doc[page_index - 1]
        blocks = cast(list[dict[str, Any]], metric["blocks"])
        text = str(metric["text"])
        char_count = int(metric["char_count"])
        block_count = int(metric["block_count"])
        used_ratio = float(metric["used_ratio"])
        blank_after_pt = float(metric["blank_after_pt"])

        if "(suite)" in text and SKILL_HEADING_RE.search(text) and not EXPERIENCE_SECTION_RE.search(text.split("(suite)", 1)[0]):
            findings.append(_issue(
                "skill_overflow_page_created",
                page_index,
                f"Bloc compétences poursuivi sur une page dédiée/suite page {page_index}",
                snippet=text[:180],
            ))

        dense_by_chars = char_count >= PAGE_DENSE_CHAR_THRESHOLD and not (char_count < 3400 and used_ratio < 0.70)
        if dense_by_chars or (block_count >= PAGE_DENSE_BLOCK_THRESHOLD and used_ratio >= 0.75):
            dense_code = "page_too_dense" if char_count >= 3600 or used_ratio >= 0.92 else "page_dense_but_acceptable"
            findings.append(_issue(
                dense_code,
                page_index,
                f"Page {page_index} anormalement dense: {char_count} caractères, {block_count} blocs",
                char_count=char_count,
                block_count=block_count,
                used_ratio=round(float(used_ratio), 3),
            ))

        sparse_last_page = page_count > 1 and page_index == page_count and char_count <= LAST_PAGE_SPARSE_CHAR_THRESHOLD and block_count <= LAST_PAGE_SPARSE_BLOCK_THRESHOLD
        underfilled_last_page = (
            page_count >= 3
            and page_index == page_count
            and char_count <= LAST_PAGE_UNDERFILLED_CHAR_THRESHOLD
            and used_ratio <= LAST_PAGE_UNDERFILLED_USED_RATIO
        )
        if sparse_last_page or underfilled_last_page:
            findings.append(_issue(
                "last_page_sparse",
                page_index,
                f"Dernière page trop peu remplie: {char_count} caractères, {block_count} blocs, hauteur utilisée {used_ratio:.0%}",
                char_count=char_count,
                block_count=block_count,
                used_ratio=round(float(used_ratio), 3),
            ))
            findings.append(_issue(
                "page_too_sparse",
                page_index,
                f"Page {page_index} trop peu remplie: {char_count} caractères, {block_count} blocs, hauteur utilisée {used_ratio:.0%}",
                char_count=char_count,
                block_count=block_count,
                used_ratio=round(float(used_ratio), 3),
            ))

        sparse_non_final = (
            page_count >= 3
            and 1 < page_index < page_count
            and (
                (used_ratio <= 0.40 and char_count <= 900)
                or (bool(metric["starts_with_suite"]) and used_ratio <= 0.45)
                or (blank_after_pt >= 430 and char_count <= 1200)
            )
        )
        if sparse_non_final:
            findings.append(_issue(
                "page_too_sparse",
                page_index,
                f"Page {page_index} trop peu remplie: {char_count} caractères, {block_count} blocs, hauteur utilisée {used_ratio:.0%}",
                char_count=char_count,
                block_count=block_count,
                used_ratio=round(float(used_ratio), 3),
                blank_after_pt=round(float(blank_after_pt), 1),
                starts_with_suite=bool(metric["starts_with_suite"]),
            ))

        in_skills_area = False
        for block_position, block in enumerate(blocks):
            block_text = _block_text(block)
            lower_text = block_text.lower()
            x0, y0, x1, y1 = [float(value) for value in block["bbox"]]
            if _looks_like_skill_heading(block_text):
                in_skills_area = True
            if in_skills_area and (_looks_like_experience_heading(block_text) or (EXPERIENCE_SECTION_RE.search(block_text) and "comp" not in lower_text)):
                in_skills_area = False

            separators = block_text.count(";") + block_text.count(",")
            if in_skills_area and (len(block_text) >= SKILL_DENSE_CHAR_THRESHOLD or separators >= SKILL_DENSE_SEPARATOR_THRESHOLD):
                if len(block_text) >= SKILL_DENSE_CHAR_THRESHOLD:
                    findings.append(_issue(
                        "skill_block_too_long",
                        page_index,
                        f"Bloc compétence trop long page {page_index}: {len(block_text)} caractères",
                        bbox=[round(value, 2) for value in (x0, y0, x1, y1)],
                        char_count=len(block_text),
                        snippet=block_text[:180],
                    ))
                findings.append(_issue(
                    "skills_too_dense",
                    page_index,
                    f"Bloc compétences trop dense page {page_index}: {len(block_text)} caractères, {separators} séparateurs",
                    bbox=[round(value, 2) for value in (x0, y0, x1, y1)],
                    char_count=len(block_text),
                    separators=separators,
                    snippet=block_text[:180],
                ))
                break

            near_bottom = y1 >= page.rect.height - EXPERIENCE_ORPHAN_BOTTOM_ZONE_PT
            remaining_text = " ".join(_block_text(candidate) for candidate in blocks[block_position + 1:])
            next_page_text = str(doc[page_index].get_text("text")) if page_index < page_count else ""
            normalized_heading = _normalize_for_fidelity(block_text)
            normalized_next_page = _normalize_for_fidelity(next_page_text)
            section_orphaned_to_suite = (
                len(block_text) <= 90
                and bool(EXPERIENCE_SECTION_RE.search(block_text))
                and len(remaining_text.strip()) < 80
                and normalized_heading
                and f"{normalized_heading} suite" in normalized_next_page
            )
            if section_orphaned_to_suite:
                findings.append(_issue(
                    "experience_section_orphan_heading",
                    page_index,
                    f"Intertitre d’expérience isolé avant une reprise en suite page {page_index + 1}",
                    bbox=[round(value, 2) for value in (x0, y0, x1, y1)],
                    snippet=block_text[:180],
                ))
                findings.append(_issue(
                    "bad_page_break",
                    page_index,
                    f"Saut de page juste après un intertitre d’expérience page {page_index}",
                    snippet=block_text[:180],
                ))
                break

            if not near_bottom or not _looks_like_experience_heading(block_text):
                continue
            opener_without_content = len(remaining_text.strip()) < 80 and bool(EXPERIENCE_SECTION_RE.search(next_page_text))
            if opener_without_content:
                findings.append(_issue(
                    "experience_orphan_heading",
                    page_index,
                    f"Titre/rôle d’expérience isolé près du bas de page {page_index}",
                    bbox=[round(value, 2) for value in (x0, y0, x1, y1)],
                    snippet=block_text[:180],
                ))
                findings.append(_issue(
                    "bad_page_break",
                    page_index,
                    f"Saut de page juste après un titre/rôle d’expérience page {page_index}",
                    snippet=block_text[:180],
                ))
                break

    return findings


PDF_ENTITY_STOPWORDS = {
    "w", "hub", "cv", "profil", "compétences", "competences", "expériences", "experiences",
    "formations", "missions", "mission", "clés", "cles", "environnement", "technique",
    "consultant", "consultante", "chef", "projet", "développeur", "developpeur", "architecte",
}


def _json_required_facts(data: dict | None) -> list[str]:
    if not isinstance(data, dict):
        return []
    facts: list[str] = []
    for exp in data.get("experiences") or []:
        if not isinstance(exp, dict):
            continue
        for key in ["date", "company_highlight"]:
            value = str(exp.get(key) or "").strip()
            if len(value) >= 4 and value not in facts:
                facts.append(value)
        for fragment in _role_fact_fragments(str(exp.get("role") or "")):
            if fragment not in facts:
                facts.append(fragment)
        for section in exp.get("sections") or []:
            if not isinstance(section, dict):
                continue
            for item in _iter_json_strings(section.get("content")):
                cleaned = str(item).strip()
                if len(cleaned) >= 4 and cleaned not in facts:
                    facts.append(cleaned)
    return facts


def _extract_pdf_source_sensitive_entities(text: str) -> list[str]:
    entities: list[str] = []
    for line in text.splitlines():
        for fragment in re.split(r"\||,|•|–|—", line):
            cleaned = re.sub(r"\s+", " ", fragment).strip(" .;:-\t")
            if len(cleaned) < 4:
                continue
            normalized = _normalize_for_fidelity(cleaned)
            if normalized in {"missions cles suite", "prestations realisee suite", "environnement technique suite", "contexte suite"} or normalized.endswith(" suite"):
                continue
            tokens = normalized.split()
            if not tokens or all(token in PDF_ENTITY_STOPWORDS for token in tokens):
                continue
            has_acronym = bool(re.search(r"\b[A-ZÉÈÀÂÊÎÔÛÄËÏÖÜÇ]{2,}\b", cleaned))
            has_title_entity = bool(re.search(r"\b(?:[A-ZÉÈÀÂÊÎÔÛÄËÏÖÜÇ][A-Za-zÀ-ÿ]+\s+){1,}[A-ZÉÈÀÂÊÎÔÛÄËÏÖÜÇA-Za-zÀ-ÿ]{2,}\b", cleaned))
            if not (has_acronym or has_title_entity):
                continue
            if cleaned not in entities:
                entities.append(cleaned)
    return entities


def find_pdf_source_fidelity_issues(text: str, source_text: str | None = None, structured_data: dict | None = None) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    pdf_normalized = _normalize_for_fidelity(text)
    source_normalized = _normalize_for_fidelity(source_text or "")

    if structured_data:
        for fact in _json_required_facts(structured_data):
            if _contains_fidelity_fact(pdf_normalized, fact):
                continue
            issues.append({
                "code": "json_fact_missing_from_pdf",
                "message": f"Fait JSON absent du PDF rendu: {fact}",
                "fact": fact,
            })

    if source_normalized:
        for location in extract_experience_location_facts(source_text or ""):
            if _contains_fidelity_fact(pdf_normalized, location):
                continue
            issues.append({
                "code": "source_experience_location_missing_from_pdf",
                "message": f"Localisation de mission source absente du PDF rendu: {location}",
                "fact": location,
            })

        for entry in extract_source_business_coverage_facts(source_text or ""):
            fact = entry["fact"]
            if _contains_fidelity_fact(pdf_normalized, fact):
                continue
            issues.append({
                "code": "source_coverage_missing_section",
                "message": f"Section source business absente du PDF rendu: {entry['section']} — {fact}",
                "section": entry["section"],
                "fact": fact,
            })

        for entity in _extract_pdf_source_sensitive_entities(text):
            if _contains_fidelity_fact(source_normalized, entity):
                continue
            issues.append({
                "code": "pdf_fact_absent_from_source",
                "message": f"Fait PDF absent du CV source: {entity}",
                "fact": entity,
            })

    return issues


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


def run_qa(pdf_path: Path, forbidden_names: list[str] | None = None, source_text: str | None = None, structured_data: dict | None = None) -> dict:
    doc = fitz.open(str(pdf_path))
    text = "\n".join(page.get_text("text") for page in doc)
    hits = []
    for name, pattern in CONTACT_PATTERNS.items():
        if re.search(pattern, text, re.I):
            hits.append(name)
    for name in forbidden_names or []:
        if name and re.search(rf"(?<![A-Za-zÀ-ÿ]){re.escape(name)}(?![A-Za-zÀ-ÿ])", text, re.I):
            hits.append(f"forbidden_name:{name}")
    bad_glyphs = any(x in text for x in ["�", "\x00"])
    content_integrity_issues = find_numbered_placeholder_repetitions(text)
    content_integrity_issues.extend(find_pdf_source_fidelity_issues(text, source_text=source_text, structured_data=structured_data))
    overflow_hits = find_text_overflow(doc)
    layout_issues = find_layout_issues(doc)
    image_sizes = []
    for page in doc:
        for img in page.get_images(full=True):
            pix = fitz.Pixmap(doc, img[0])
            image_sizes.append([pix.width, pix.height])
    has_logo = [1051, 398] in image_sizes
    has_watermark = [1192, 1192] in image_sizes
    report = {
        "passed": not hits and not bad_glyphs and not content_integrity_issues and not overflow_hits and not layout_issues and has_logo and has_watermark and doc.page_count > 0,
        "pages": doc.page_count,
        "contact_hits": hits,
        "bad_glyphs": bad_glyphs,
        "content_integrity_issues": content_integrity_issues,
        "text_overflow_hits": overflow_hits,
        "layout_issues": layout_issues,
        "has_logo": has_logo,
        "has_watermark": has_watermark,
    }
    if not report["passed"]:
        raise QAError(report)
    return report
