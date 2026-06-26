from __future__ import annotations

import re
from dataclasses import dataclass


LAYOUT_ONLY_RE = re.compile(
    r"\b(remont(?:e|er)|descend(?:s|re)?|d[eé]plac(?:e|er)|mets?|mettre|page\s*\d+|derni[eè]re\s+page|saut(?:s)?\s+de\s+page|a[eé]rer|resserrer|compacter|remonter|mont(?:e|er)|rapproch(?:e|er))\b",
    re.I,
)
CONTENT_CHANGE_RE = re.compile(
    r"\b(ajout(?:e|er)|supprim(?:e|er)|corrig(?:e|er)\s+le\s+texte|modifi(?:e|er)\s+le\s+texte|r[eé][eé]cris|r[eé]dige|enl[eè]ve|change\s+la\s+mission|manquant|oubli[eé]|rajout(?:e|er)|compl[eé]ter)\b",
    re.I,
)
RESET_RE = re.compile(
    r"\b(repart(?:ir|ons)?\s+de\s+z[eé]ro|refaire\s+de\s+z[eé]ro|tout\s+refaire|repartir\s+du\s+source)\b",
    re.I,
)


@dataclass(frozen=True)
class RevisionIntent:
    kind: str  # "layout_only" | "content" | "reset" | "unknown"
    reason: str


def classify_revision_intent(body: str) -> RevisionIntent:
    text = " ".join((body or "").split())
    if not text:
        return RevisionIntent("unknown", "empty")
    if RESET_RE.search(text):
        return RevisionIntent("reset", "reset_keywords")
    has_layout = bool(LAYOUT_ONLY_RE.search(text))
    has_content = bool(CONTENT_CHANGE_RE.search(text))
    if has_layout and not has_content:
        return RevisionIntent("layout_only", "layout_keywords")
    if has_content and not has_layout:
        return RevisionIntent("content", "content_keywords")
    if has_layout and has_content:
        return RevisionIntent("content", "mixed_content_priority")
    return RevisionIntent("unknown", "no_specific_match")
