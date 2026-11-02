"""Detect gibberish text layers (broken PDF font maps) before structuring."""
import re

# Share of word-like tokens below which the native text layer is unusable.
# Test bank (2026-11-02): real CVs score 0.85-0.96; a PDF whose fonts map
# glyphs to private codes (Benjamin) scores 0.05.
READABILITY_OCR_THRESHOLD = 0.5
_WORD_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’\-]*$")
_VOWEL_RE = re.compile(r"[aeiouyàâäéèêëîïôöùûüAEIOUYÀÂÉÈÊËÎÏÔÖÙÛÜ]")


def text_readability(text: str) -> float:
    """Return the share of tokens that look like natural-language words."""
    tokens = [token.strip(".,;:()[]«»\"!?/") for token in (text or "").split()]
    tokens = [token for token in tokens if len(token) >= 2]
    if not tokens:
        return 0.0
    words = sum(1 for token in tokens if _WORD_RE.match(token) and _VOWEL_RE.search(token))
    return words / len(tokens)
