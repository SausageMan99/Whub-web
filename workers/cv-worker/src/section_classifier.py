from __future__ import annotations

import re

from .content_blocks import BlockType, ContentBlock, SourceDocument

_HEADER_RULES: list[tuple[re.Pattern[str], BlockType]] = [
    (re.compile(r"\b(exp[ée]riences?|parcours|missions?)\b", re.IGNORECASE), "experience"),
    (re.compile(r"\b(comp[ée]tences?|skills?|technologies?)\b", re.IGNORECASE), "skills"),
    (re.compile(r"\b(formations?|dipl[oô]mes?|education)\b", re.IGNORECASE), "education"),
    (re.compile(r"\b(langues?)\b", re.IGNORECASE), "languages"),
    (re.compile(r"\b(certifications?)\b", re.IGNORECASE), "certifications"),
]

_DATE_RE = re.compile(r"\b(19|20)\d{2}\b.*\b(19|20)\d{2}|\baujourd[’']?hui\b", re.IGNORECASE)
_ROLE_RE = re.compile(r"\b(d[ée]veloppeur|consultant|architecte|ing[ée]nieur|chef de projet|tech lead|lead)\b", re.IGNORECASE)


def _header_type(text: str) -> BlockType | None:
    normalized = " ".join(text.strip().split())
    if len(normalized) > 80:
        return None
    for pattern, block_type in _HEADER_RULES:
        if pattern.search(normalized):
            return block_type
    return None


def _looks_like_experience(text: str) -> bool:
    return bool(_DATE_RE.search(text) and _ROLE_RE.search(text))


def _replace_type(block: ContentBlock, block_type: BlockType) -> ContentBlock:
    return ContentBlock.from_text(
        block_type,
        source_order=block.source_order,
        page=block.page,
        text=block.text,
        confidence=block.confidence,
        required=block.required,
        bbox=block.bbox,
    )


def classify_sections(document: SourceDocument) -> SourceDocument:
    current_type: BlockType = "other"
    classified: list[ContentBlock] = []
    for block in document.ordered_blocks():
        header = _header_type(block.text)
        if header:
            current_type = header
            classified.append(_replace_type(block, "other"))
            continue
        block_type = "experience" if _looks_like_experience(block.text) else current_type
        classified.append(_replace_type(block, block_type))
    return SourceDocument(
        blocks=classified,
        source_profile=document.source_profile,
        raw_chars=document.raw_chars,
        sanitized_chars=document.sanitized_chars,
    )
