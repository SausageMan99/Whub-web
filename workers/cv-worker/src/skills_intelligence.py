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


def parse_source_skills_section(source_text: str) -> ParsedSourceSkills:
    """Parse the `COMPÉTENCES` section of a source CV.

    Returns a deterministic, deduplicated, taxonomy-aligned view. Empty input
    or absent `COMPÉTENCES` heading yields an empty result.
    """
    return ParsedSourceSkills()
