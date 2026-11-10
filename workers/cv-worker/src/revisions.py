from __future__ import annotations

import re
from dataclasses import dataclass


LAYOUT_ONLY_RE = re.compile(
    r"\b(remont(?:e|er)|descend(?:s|re)?|d[eé]plac(?:e|er)|mets?|mettre|page\s*\d+|derni[eè]re\s+page|saut(?:s)?\s+de\s+page|a[eé]rer|resserrer|compacter|remonter|mont(?:e|er)|rapproch(?:e|er)"
    r"|moins\s+de\s+pages?|r[ée][ée]quilibr\w*|mise\s+en\s+page)\b",
    re.I,
)
CONTENT_CHANGE_RE = re.compile(
    r"\b(mets?\s+en\s+avant|mettre\s+en\s+avant|ajout(?:e|er)|supprim(?:e|er)|corrig(?:e|er)\s+le\s+texte|modifi(?:e|er)\s+le\s+texte|r[eé][eé]cris|r[eé]dige|enl[eè]ve|change\s+la\s+mission|manquant|oubli[eé]|rajout(?:e|er)|compl[eé]ter|comp[ée]tences?|cat[ée]gor(?:ie|ies)|stack|technolog(?:ie|ies))\b",
    re.I,
)
RESET_RE = re.compile(
    r"\b(repart(?:ir|ons)?\s+de\s+z[eé]ro|refaire\s+de\s+z[eé]ro|tout\s+refaire|repartir\s+du\s+source)\b",
    re.I,
)


SKILLS_TARGET_RE = re.compile(
    r"\b(comp[ée]tences?|skills?|cat[ée]gor(?:ie|ies)|stack|technolog(?:ie|ies)|outils?|doublons?)\b",
    re.I,
)
# "Mettre les compétences en page 2" names the skills but only moves them.
SKILLS_EDIT_RE = re.compile(
    r"\b(supprim\w*|retir\w*|enl[eè]v\w*|nettoi\w*|nettoy\w*|ajout\w*|rajout\w*|corrig\w*|modifi\w*|remplac\w*"
    r"|renomm\w*|regroup\w*|fusionn\w*|s[ée]par\w*|class\w*|d[ée]doublonn\w*|doublons?|m[ée]lang\w*)\b",
    re.I,
)


# Lot 4 (2026-11): reviewer requests about pagination. In production
# « Fais tenir le CV sur moins de pages » (x3), « Rééquilibre la mise en
# page » (x2), « remonter les expériences … pour pas laisser un gros vide »,
# « vérifie bien les sauts de page » changed nothing: none of them was
# recognised, the CV was structured again by the model (which cannot move a
# page break) and rendered with the same options. They now set a pagination
# goal handled by renderer variants (src/layout/pagination.py), with or
# without a content change in the same comment.
FEWER_PAGES_RE = re.compile(
    r"\bmoins\s+de\s+pages?\b|\btrop\s+(?:de\s+pages|long)\b|\br[ée]dui\w*\s+(?:le\s+nombre\s+de\s+pages|[àa]\s+\d+\s+pages?)"
    r"|\btenir\s+(?:sur|en)\s+(?:une|un|deux|trois|\d+)\s+pages?\b|\b(?:une|deux|trois|\d+)\s+pages?\s+(?:maximum|max)\b"
    r"|\bplus\s+court\b|\bcompact\w*\b|\bresserr\w*\b|\bderni[eè]re\s+page\s+(?:presque\s+)?vide\b",
    re.I,
)
REBALANCE_RE = re.compile(
    r"\br[ée][ée]quilibr\w*|\b[ée]quilibr\w*|\b(?:gros|grand|trop\s+de)\s+(?:vide|blanc|espace)s?\b|\bespaces?\s+vides?\b"
    r"|\bpages?\s+(?:[àa]\s+moiti[ée]\s+)?vides?\b|\bsauts?\s+de\s+pages?\b|\bremont\w*\s+(?:les?\s+|l')?exp[ée]riences?\b"
    r"|\bmise\s+en\s+page\b",
    re.I,
)


def pagination_request(comments: list[dict] | list[str] | None) -> str | None:
    """"fewer_pages", "rebalance" or None for the unresolved revision comments.

    "fewer_pages" wins when both are asked: fewer pages also removes blank."""
    goal: str | None = None
    for comment in comments or []:
        if isinstance(comment, dict):
            if comment.get("comment_type") not in (None, "revision"):
                continue
            body = str(comment.get("body") or "")
        else:
            body = str(comment or "")
        text = " ".join(body.split())
        if FEWER_PAGES_RE.search(text):
            return "fewer_pages"
        if REBALANCE_RE.search(text):
            goal = "rebalance"
    return goal


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


def requests_skills_revision(comments: list[dict] | None) -> bool:
    """True when an unresolved revision comment asks to change the skills content.

    The deterministic "source wins" passes (source skills merge, coverage-fact
    reinjection, visual skills override) must then let the model's answer to
    the comment stand, or the comment has no effect.
    """
    for comment in comments or []:
        if not isinstance(comment, dict) or comment.get("comment_type") != "revision":
            continue
        body = str(comment.get("body") or "")
        if (
            classify_revision_intent(body).kind == "content"
            and SKILLS_TARGET_RE.search(body)
            and SKILLS_EDIT_RE.search(body)
        ):
            return True
    return False
