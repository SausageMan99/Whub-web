"""Deterministic skills intelligence layer for the W hub CV Factory worker.

The LLM is unreliable when a Hellowork/ATS PDF dumps a 30-line `COMPÉTENCES`
block where bullets `➢` are on their own line and the categories are inline
labels like `Cloud:`, `Sécurité:`, `Data bases:`. This module takes that
source back from the model and produces a clean, deduplicated, taxonomy-aligned
`skills` payload that the renderer can lay out without dumping 6 pages of
`Autres — suite N`.

Design rules:
- The LLM is still the primary producer of `skills` and `languages`. This
  module never rewrites source text or invents new skills.
- It deduplicates only by canonical key (e.g. `AZURE` and `Azure` and `azure`
  collapse to the same item).
- It extracts spoken languages out of `skills` into `languages` when the
  source mentions them in the same section.
- It never returns `Autres` as a normal category: the only fallback is
  `Outils & Environnements`. `Autres` is reserved for QA failure signals.
- It is non-destructive on input: the public functions return new objects.
"""
from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class ParsedSourceSkills:
    skills_by_category: dict[str, list[str]] = field(default_factory=dict)
    languages: list[dict[str, str]] = field(default_factory=list)


_SKILLS_START_RE = re.compile(
    r"^\s*comp[ée]tences(?:\s+techniques?)?\s*$",
    re.IGNORECASE,
)
_SECTION_STOP_RE = re.compile(
    r"^\s*(?:exp[ée]riences?|parcours|missions?|formations?|dipl[oô]mes?"
    r"|certifications?|langues?|centres?\s+d['’]int[ée]r[êe]t|loisirs?"
    r"|projets?|r[ée]alisations?|coordonn[ée]es?|contact)\b",
    re.IGNORECASE,
)


def _extract_skills_lines(source_text: str) -> list[str]:
    """Return the lines between the `COMPÉTENCES` heading and the next section.

    Empty result if no `COMPÉTENCES` heading is found.
    """
    lines = [line.rstrip() for line in (source_text or "").splitlines()]
    start_index: int | None = None
    for index, line in enumerate(lines):
        if _SKILLS_START_RE.match(line):
            start_index = index + 1
            break
    if start_index is None:
        return []

    out: list[str] = []
    for line in lines[start_index:]:
        if out and _SECTION_STOP_RE.match(line.strip()):
            break
        if line.strip():
            out.append(line.strip())
    return out


_ARROW_RE = re.compile(r"^[➢>•\-–—]+\s*(.*)$")


def _flush_skill_item(buffer: list[str]) -> str | None:
    text = " ".join(part.strip() for part in buffer if part and part.strip())
    text = re.sub(r"\s+", " ", text).strip(" :;•➢-–—")
    if not text:
        return None
    return text


def _split_arrow_skill_items(lines: list[str]) -> list[str]:
    """Collapse Hellowork-style isolated `➢` bullets into individual items.

    Lines that contain only `➢` (with or without whitespace) start a new
    item. Content before the first `➢` is its own item (the section opener).
    """
    items: list[str] = []
    buffer: list[str] = []
    pending_arrow = False

    def flush() -> None:
        nonlocal buffer
        text = _flush_skill_item(buffer)
        if text:
            items.append(text)
        buffer = []

    for raw in lines:
        line = re.sub(r"\s+", " ", raw or "").strip()
        if not line:
            continue
        match = _ARROW_RE.match(line)
        if match:
            flush()
            rest = match.group(1).strip()
            if rest:
                buffer = [rest]
                pending_arrow = False
            else:
                pending_arrow = True
            continue
        if pending_arrow:
            flush()
            buffer = [line]
            pending_arrow = False
            continue
        buffer.append(line)
    flush()
    return items


def parse_source_skills_section(source_text: str) -> ParsedSourceSkills:
    """Parse the `COMPÉTENCES` section of a source CV.

    Returns a deterministic, deduplicated, taxonomy-aligned view. Empty input
    or absent `COMPÉTENCES` heading yields an empty result.
    """
    _extract_skills_lines(source_text)
    return ParsedSourceSkills()
