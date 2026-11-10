"""Réparations typographiques sûres du texte extrait (lot 5, 2026-11).

Défauts vus dans les CV livrés, venus du PDF source :
- ligatures perdues : une police sans table Unicode pour « ﬀ/ﬁ/ﬂ/ﬃ/ﬄ » rend
  la ligature comme une espace (« di érents », « e ectuer », « a n de ») ;
- lettre capitale détachée (« L ead », « D éveloppement ») ;
- espace manquante après un point (« métiers.Cette »).

Chaque réparation est volontairement étroite : une ligature n'est rétablie que
si le mot obtenu commence par un radical connu (LIGATURE_STEMS) ; une capitale
n'est recollée que si le reste n'est pas un mot du document. Les fonctions
`find_*` servent à la QA et au banc pour compter ce qui reste.
"""
from __future__ import annotations

import re
from typing import Iterable

# Most frequent first: "a n de" is "afin de", not "affin de".
LIGATURES = ("fi", "ff", "fl", "ffi", "ffl")

# Radicaux de mots (français et anglais courants dans un CV) contenant une
# ligature. Le mot recollé doit commencer par l'un d'eux, ligature comprise.
LIGATURE_STEMS = (
    # ff
    "différ", "diffus", "diffic", "effect", "effic", "effort", "effet", "effectu", "offre", "offri",
    "offert", "offic", "offshore", "affich", "affair", "affect", "affirm", "affili", "suffi",
    "chiffr", "staff", "suffisa", "coeffic", "souffl", "étoff", "afflu", "traffic", "difference", "different",
    "effective", "efficien", "offer", "office", "staffing", "diffusion", "buffer",
    # fi
    "afin", "profil", "profit", "fichier", "fiche", "financ", "final", "finit", "finir", "finis", "filia",
    "filtr", "filière", "filiere", "confi", "certifi", "spécifi", "specifi", "modifi", "identifi",
    "justifi", "simplifi", "classifi", "vérifi", "verifi", "qualifi", "planifi", "notifi", "unifi",
    "fidél", "fidel", "fiab", "bénéfi", "benefi", "défi", "signifi", "diversifi", "intensifi", "rectifi",
    "amplifi", "magnifi", "fiscal", "firewall", "first", "field", "file", "fix", "artifi", "scientifi",
    "configur", "définition", "definition", "officiel", "fiction", "fibre", "fiber",
    # fl
    "flux", "flex", "fluid", "flott", "flotte", "flow", "workflow", "réflex", "reflex", "réfléch",
    "reflet", "infl", "confl", "flash", "fleet", "flag", "superflu",
)

# Mots courts qui existent seuls : deux d'entre eux côte à côte ne sont pas
# un mot coupé (« de la », « e et » reste réparable car « e » n'en est pas un).
COMMON_WORDS = frozenset("""
a à et de du des le la les l un une en ou au aux sur par pour avec dans ce ces se sa son ses
qui que ne pas plus est sont été the and of in to for with on at an is it as by or be from
y il elle on nous vous ils mes tes leur leurs mon ma ta
""".split())

_LETTER = r"[^\W\d_]"
# Paire « fragment fragment » ; le second est en lecture anticipée pour que
# « les di érents » teste aussi la paire « di érents ».
_LIGATURE_PAIR_RE = re.compile(rf"(?<![\w])({_LETTER}{{1,14}}) (?=({_LETTER}{{1,24}})(?![\w]))")


def _ligature_join(left: str, right: str) -> str | None:
    """Mot recollé si `left` + ligature + `right` donne un mot connu."""
    if not right[:1].islower():
        return None
    if left.lower() in COMMON_WORDS and right.lower() in COMMON_WORDS:
        return None
    for lig in LIGATURES:
        joined = f"{left}{lig}{right}"
        low = joined.lower()
        for stem in LIGATURE_STEMS:
            # Enough of the stem is checked outside the ligature: "in" + "fl"
            # + "banking" is not "infl…".
            checked = len(stem) - len(left) - len(lig)
            if low.startswith(stem) and checked >= 0 and (
                checked >= 2 or low == stem
                or (len(stem) - len(lig) >= 3 and left.lower() not in COMMON_WORDS)
            ):
                return joined
    return None


# Ligature perdue en tête de mot (« le chier » -> « le fichier ») : seulement
# des débuts qui ne commencent aucun mot (« lead », « agents », « délais »
# restent intacts).
_LIGATURE_START_FRAGMENTS = (
    ("chier", "fi"), ("nanc", "fi"), ("nal", "fi"), ("ltr", "fi"), ("lière", "fi"), ("lial", "fi"),
    ("abilit", "fi"), ("rewall", "fi"), ("délit", "fi"), ("scalit", "fi"), ("otte", "fl"),
)


def _ligature_prefix(right: str) -> str | None:
    """`right` précédé de sa ligature initiale perdue (« chier » -> « fichier »)."""
    low = right.lower()
    if len(right) < 3 or not right[:1].islower() or low in COMMON_WORDS:
        return None
    for fragment, lig in _LIGATURE_START_FRAGMENTS:
        if low.startswith(fragment):
            return lig + right
    return None


def _ligature_candidates(text: str):
    """(start, end, replacement) des ligatures perdues, sans chevauchement."""
    out = []
    for match in _LIGATURE_PAIR_RE.finditer(text):
        left, right = match.group(1), match.group(2)
        joined = _ligature_join(left, right)
        if joined:
            out.append((match.start(), match.end(2), joined))
            continue
        if left.lower() in COMMON_WORDS:
            prefixed = _ligature_prefix(right)
            if prefixed:
                out.append((match.start(2), match.end(2), prefixed))
    return out


def repair_broken_ligatures(text: str) -> tuple[str, int]:
    """(texte réparé, nombre de réparations)."""
    if not text or " " not in text:
        return text, 0
    count = 0
    # Les paires se chevauchent (« les di érents ») : on répète jusqu'à
    # stabilité, chaque passe ne remplaçant que des paires disjointes.
    for _ in range(4):
        candidates = _ligature_candidates(text)
        if not candidates:
            break
        pieces, last = [], 0
        for start, end, repl in candidates:
            if start < last:
                continue
            pieces.append(text[last:start])
            pieces.append(repl)
            last = end
            count += 1
        pieces.append(text[last:])
        text = "".join(pieces)
    return text, count


def find_broken_ligatures(text: str) -> list[str]:
    """Mots coupés par une ligature perdue, tels qu'ils apparaissent."""
    return [text[start:end] for start, end, _ in _ligature_candidates(text or "")]


# --------------------------------------------------------------- capitales

_DETACHED_CAPITAL_RE = re.compile(r"(?:(?<=\s)|(?<=^)|(?<=[(«\"“]))([A-ZÀ-ÖØ-Þ]) ([a-zà-öø-ÿ]{3,})(?![^\W\d_])")
# Lettres qui sont un mot à elles seules (« A travers », « Y compris », « O »).
_SINGLE_LETTER_WORDS = {"A", "À", "Y", "O", "I"}


def text_vocabulary(texts: Iterable[str]) -> set[str]:
    """Mots (minuscules) des textes, sans ceux qui suivent une capitale
    détachée : « L ead » ne doit pas faire de « ead » un mot."""
    vocab: set[str] = set()
    for text in texts:
        cleaned = _DETACHED_CAPITAL_RE.sub(" ", str(text or ""))
        vocab.update(w.lower() for w in re.findall(rf"{_LETTER}+", cleaned))
    return vocab


def _detached_capital_candidates(text: str, vocabulary: set[str]):
    out = []
    for match in _DETACHED_CAPITAL_RE.finditer(text):
        letter, rest = match.group(1), match.group(2)
        if letter in _SINGLE_LETTER_WORDS:
            continue
        if rest.lower() in COMMON_WORDS or rest.lower() in vocabulary:
            continue
        out.append((match.start(), match.end(), letter + rest))
    return out


def repair_detached_capitals(text: str, vocabulary: set[str]) -> tuple[str, int]:
    """« L ead » -> « Lead » quand « ead » n'est pas un mot du document."""
    candidates = _detached_capital_candidates(text or "", vocabulary)
    if not candidates:
        return text, 0
    pieces, last = [], 0
    for start, end, repl in candidates:
        pieces.append(text[last:start])
        pieces.append(repl)
        last = end
    pieces.append(text[last:])
    return "".join(pieces), len(candidates)


def find_detached_capitals(text: str, vocabulary: set[str]) -> list[str]:
    return [text[s:e] for s, e, _ in _detached_capital_candidates(text or "", vocabulary)]


# --------------------------------------------------------------- ponctuation

# Mot entièrement en minuscules, point collé à un mot capitalisé :
# « métiers.Cette ». « Office.Interop », « ASP.NET », « Vue.js » ne bougent pas.
_MISSING_SPACE_RE = re.compile(r"(?:(?<=\s)|(?<=^))([a-zà-öø-ÿ][a-zà-öø-ÿ'’-]{2,})([.!?;])([A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]{2,})(?![^\W\d_.])")


def repair_missing_space_after_punctuation(text: str) -> tuple[str, int]:
    if not text:
        return text, 0
    return _MISSING_SPACE_RE.subn(r"\1\2 \3", text)


def find_missing_space_after_punctuation(text: str) -> list[str]:
    return [m.group(0) for m in _MISSING_SPACE_RE.finditer(text or "")]
