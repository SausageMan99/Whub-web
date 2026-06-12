from __future__ import annotations

from dataclasses import dataclass
from typing import List

import re

from .content_blocks import ContentBlock, SourceDocument

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?:(?:\+33|0)\s*[1-9](?:[\s.-]*\d{2}){4})")
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[^\s,;]+", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s,;]+", re.IGNORECASE)


@dataclass(frozen=True)
class SanitizedBlockResult:
    block: ContentBlock
    report: dict[str, int]


@dataclass(frozen=True)
class SanitizedDocumentResult:
    document: SourceDocument
    report: dict[str, int]


def _remove_pattern(text: str, pattern: re.Pattern[str]) -> tuple[str, int]:
    return pattern.subn("", text)


def sanitize_block(
    block: ContentBlock,
    *,
    candidate_first_name: str,
    forbidden_identity_terms: list[str],
) -> SanitizedBlockResult:
    text = block.text
    report = {
        "removed_email_count": 0,
        "removed_phone_count": 0,
        "removed_linkedin_count": 0,
        "removed_url_count": 0,
        "removed_identity_terms_count": 0,
    }

    text, count = _remove_pattern(text, _LINKEDIN_RE)
    report["removed_linkedin_count"] += count
    text, count = _remove_pattern(text, _EMAIL_RE)
    report["removed_email_count"] += count
    text, count = _remove_pattern(text, _PHONE_RE)
    report["removed_phone_count"] += count
    text, count = _remove_pattern(text, _URL_RE)
    report["removed_url_count"] += count

    for term in forbidden_identity_terms:
        safe = term.strip()
        if not safe or safe.lower() == candidate_first_name.strip().lower():
            continue
        text, count = re.subn(rf"\b{re.escape(safe)}\b", "", text, flags=re.IGNORECASE)
        report["removed_identity_terms_count"] += count

    cleaned_lines = [" ".join(line.split()) for line in text.splitlines()]
    cleaned = "\n".join(line for line in cleaned_lines if line.strip())
    sanitized = ContentBlock.from_text(
        block.type,
        source_order=block.source_order,
        page=block.page,
        text=cleaned,
        confidence=block.confidence,
        required=block.required,
        bbox=block.bbox,
    )
    return SanitizedBlockResult(block=sanitized, report=report)


def sanitize_document(
    document: SourceDocument,
    *,
    candidate_first_name: str,
    forbidden_identity_terms: list[str],
) -> SanitizedDocumentResult:
    blocks: list[ContentBlock] = []
    total = {
        "removed_email_count": 0,
        "removed_phone_count": 0,
        "removed_linkedin_count": 0,
        "removed_url_count": 0,
        "removed_identity_terms_count": 0,
    }
    for block in document.ordered_blocks():
        result = sanitize_block(
            block,
            candidate_first_name=candidate_first_name,
            forbidden_identity_terms=forbidden_identity_terms,
        )
        blocks.append(result.block)
        for key, value in result.report.items():
            total[key] += value
    sanitized = SourceDocument(
        blocks=blocks,
        source_profile=document.source_profile,
        raw_chars=sum(b.char_count for b in document.blocks),
        sanitized_chars=sum(b.char_count for b in blocks),
    )
    return SanitizedDocumentResult(document=sanitized, report=total)
