"""Passe de finition déterministe du contenu du CV (lots 3 et 5, 2026-11).

Appliquée au JSON structuré juste avant la mise en page (src/main.py, après
le nettoyage des compétences), idempotente. Elle ne réécrit pas le fond :

- valeurs vides ou de remplissage (« Non spécifié », « () », « N/A ») retirées ;
- restes d'en-tête/pied de page du CV source (« Page 2 / 4 », texte en lettres
  espacées, « Prénom · titre ») retirés du contenu ;
- typographie : ligatures perdues, capitale détachée, espace après un point,
  marqueurs de puce en double (« o », « -> », « • »), virgule finale ;
- dates au format commun « Juin 2026 – Déc. 2026 » / « 2019 – 2021 » /
  « Mars 2025 – Aujourd'hui », « 2019 – 2019 » -> « 2019 » ;
- expériences en ordre antichronologique (poste en cours d'abord), en-têtes
  d'expérience répétés fusionnés, phrase de contexte sortie du champ société ;
- avec le texte source : puce coupée en deux recollée, mot coupé complété,
  mot manquant rétabli (« sections du, avec » -> « sections du site web, avec »).

Tout ce qui est retiré ou modifié est inscrit dans le journal
`_content_warnings` (src/content_log.py). Les fonctions `find_*` détectent
sans modifier : la QA (src/qa.py) et le banc d'essai s'en servent.
"""
from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from datetime import date
from typing import Any, Iterable

from .content_log import add_content_warning
from .text_repair import (
    find_broken_ligatures,
    repair_broken_ligatures,
    repair_detached_capitals,
    repair_missing_space_after_punctuation,
    text_vocabulary,
)

# ------------------------------------------------------------------ helpers


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).lower().replace("’", "'")
    text = re.sub(r"[^0-9a-zà-ÿ+#]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


# ------------------------------------------------------------------ placeholders

PLACEHOLDER_RE = re.compile(
    r"^\s*(?:non\s+sp[ée]cifi[ée]e?s?|non\s+renseign[ée]e?s?|non\s+communiqu[ée]e?s?|non\s+pr[ée]cis[ée]e?s?|"
    r"p[ée]riode\s+non\s+sp[ée]cifi[ée]e|date\s+non\s+sp[ée]cifi[ée]e|n\s*/\s*a|n\.a\.?|inconnue?|unknown|"
    r"not\s+specified|none|null|[-–—?]+)\s*$",
    re.I,
)
_INLINE_PLACEHOLDER_RE = re.compile(
    r"\s*\(\s*(?:non\s+sp[ée]cifi[ée]e?s?|non\s+renseign[ée]e?s?|n\s*/\s*a)\s*\)", re.I
)
_EMPTY_PARENS_RE = re.compile(r"\s*\(\s*[,;:.\-–—/]*\s*\)")


def is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and bool(PLACEHOLDER_RE.match(value)) and value.strip() != ""


# ------------------------------------------------------------------ furniture

_PAGE_MARKER_RE = re.compile(r"(?i)\bpage\s+\d{1,3}\s*(?:/|sur|of|·|-)\s*\d{1,3}\b|\bpage\s+\d{1,3}\b(?=\s*$)")
# Five single characters or more separated by one or two spaces:
# "D O S S I E R  D E  C O M P É T E N C E S", "Q A  E n g i n e e r".
_LETTER_SPACED_RE = re.compile(r"(?<!\S)(?:[^\W\d_&]|&) {1,2}(?:(?:[^\W\d_&]|&) {1,2}){3,}(?:[^\W\d_&]|&)(?!\S)")


def _strip_furniture(text: str, furniture: list[str]) -> str:
    out = _PAGE_MARKER_RE.sub(" ", text)
    out = _LETTER_SPACED_RE.sub(" ", out)
    for line in furniture:
        # Section titles repeated on later pages ("Expériences
        # professionnelles") are not stripped from content: running headers
        # and footers are longer.
        if len(line.split()) >= 4 and line in out:
            out = out.replace(line, " ")
    return out


# ------------------------------------------------------------------ bullets

_BULLET_MARKER_RE = re.compile(r"^\s*(?:(?:[•▪◦●■➢✓►▸*·]|->|→|=>|[-–—](?=\s)|o(?=\s+\S))\s*)+")


def strip_bullet_marker(text: str) -> str:
    return _BULLET_MARKER_RE.sub("", text)


# ------------------------------------------------------------------ dates

_MONTHS = {
    1: ("janvier", "janv", "jan", "january"),
    2: ("février", "fevrier", "févr", "fevr", "fév", "fev", "feb", "february"),
    3: ("mars", "mar", "march"),
    4: ("avril", "avri", "avr", "apr", "april"),
    5: ("mai", "may"),
    6: ("juin", "jun", "june"),
    7: ("juillet", "juil", "jul", "july"),
    8: ("août", "aout", "aug", "august"),
    9: ("septembre", "sept", "sep", "september"),
    10: ("octobre", "oct", "october"),
    11: ("novembre", "nov", "november"),
    12: ("décembre", "decembre", "déc", "dec", "december"),
}
MONTH_LABELS = {
    1: "Janv.", 2: "Févr.", 3: "Mars", 4: "Avr.", 5: "Mai", 6: "Juin",
    7: "Juil.", 8: "Août", 9: "Sept.", 10: "Oct.", 11: "Nov.", 12: "Déc.",
}
PRESENT_LABEL = "Aujourd'hui"
_MONTH_LOOKUP = {name: number for number, names in _MONTHS.items() for name in names}
_MONTH_ALT = "|".join(sorted((re.escape(n) for n in _MONTH_LOOKUP), key=len, reverse=True))
_PRESENT_RE = r"aujourd['’]?\s*hui|[àa]\s+ce\s+jour|ce\s+jour|pr[ée]sent|present|actuel(?:lement)?|en\s+cours|now|current|today|maintenant|to\s+date"
_QUALIFIER_RE = r"(?:fin|d[ée]but|mi|courant|late|early|mid)"
_POINT_RE = re.compile(
    rf"(?P<present>{_PRESENT_RE})"
    rf"|(?:(?P<qual>{_QUALIFIER_RE})[\s-]+)?(?:"
    rf"(?:(?P<day>\d{{1,2}})[/.-])?(?P<mnum>\d{{1,2}})[/.-](?P<y1>(?:19|20)\d{{2}})"
    rf"|(?P<mname>{_MONTH_ALT})\.?\s*(?P<y2>(?:19|20)\d{{2}})"
    rf"|(?P<y3>(?:19|20)\d{{2}})"
    rf")",
    re.I,
)
_RANGE_SEP_RE = re.compile(r"^\s*(?:[-–—]+|->|→|=>|/|à|a|au|to|until|jusqu['’]?\s*(?:à|au|en)|et)?\s*$", re.I)
_LEAD_RE = re.compile(r"^\s*(?:(?P<since>depuis|since)\s+|(?:de|du|from)\s+|d['’]\s*)", re.I)


class _Point:
    __slots__ = ("year", "month", "present", "qualifier")

    def __init__(self, year=None, month=None, present=False, qualifier=""):
        self.year, self.month, self.present, self.qualifier = year, month, present, qualifier

    def label(self) -> str:
        if self.present:
            return PRESENT_LABEL
        base = f"{MONTH_LABELS[self.month]} {self.year}" if self.month else str(self.year)
        if self.qualifier:
            return f"{self.qualifier.capitalize()} {base}"
        return base

    def key(self, end: bool) -> tuple[int, int]:
        if self.present:
            return (9999, 12)
        return (self.year, self.month or (12 if end else 1))


def _parse_point(match: re.Match[str]) -> _Point | None:
    if match.group("present"):
        return _Point(present=True)
    qual = (match.group("qual") or "").lower()
    if match.group("y1"):
        month = int(match.group("mnum"))
        if not 1 <= month <= 12:
            return None
        return _Point(int(match.group("y1")), month, qualifier=qual)
    if match.group("y2"):
        month = _MONTH_LOOKUP.get(match.group("mname").lower().rstrip("."))
        return _Point(int(match.group("y2")), month, qualifier=qual) if month else None
    return _Point(int(match.group("y3")), None, qualifier=qual)


def parse_date_text(value: str) -> dict | None:
    """{"start", "end", "ongoing", "suffix"} for a CV date, None when it
    does not read as one or two dates (left as written)."""
    text = _collapse(value)
    if not text:
        return None
    suffix = ""
    suffix_match = re.search(r"(\s*\([^()]*\))+\s*$", text)
    if suffix_match:
        suffix = _collapse(suffix_match.group(0))
        text = text[: suffix_match.start()].strip()
    since = False
    lead = _LEAD_RE.match(text)
    if lead:
        since = bool(lead.group("since"))
        text = text[lead.end():]
    # "2024-26": two-digit end year.
    short = re.fullmatch(r"((?:19|20)(\d{2}))\s*[-–—/]\s*(\d{2})", text)
    if short and int(short.group(3)) >= int(short.group(2)):
        text = f"{short.group(1)} – {short.group(1)[:2]}{short.group(3)}"
    points: list[_Point] = []
    position = 0
    for match in _POINT_RE.finditer(text):
        between = text[position:match.start()]
        if (points and not _RANGE_SEP_RE.match(between)) or (not points and between.strip()):
            return None
        point = _parse_point(match)
        if point is None:
            return None
        points.append(point)
        position = match.end()
    if text[position:].strip(" .,;") or not points or len(points) > 2:
        return None
    if since and len(points) == 1:
        points.append(_Point(present=True))
    start = points[0]
    end = points[1] if len(points) == 2 else None
    if start.present:
        return None
    return {"start": start, "end": end, "ongoing": bool(end and end.present), "suffix": suffix}


def format_date_text(value: str) -> str:
    """Common date format; the original (spaces collapsed) when unreadable."""
    parsed = parse_date_text(value)
    if not parsed:
        return _collapse(value)
    start, end = parsed["start"], parsed["end"]
    label = start.label()
    if end is not None and end.label() != label:
        label = f"{label} – {end.label()}"
    if parsed["suffix"]:
        label = f"{label} {parsed['suffix']}"
    return label


def date_sort_key(value: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """(end, start) for an antichronological sort; None when unreadable."""
    parsed = parse_date_text(value)
    if not parsed:
        return None
    start = parsed["start"]
    end = parsed["end"] or start
    return (end.key(True), start.key(False))


def date_format_signature(value: str) -> str:
    """Shape of a date string (digits -> 9, letters -> M): the banc counts
    distinct shapes per CV."""
    shape = re.sub(r"\d", "9", _collapse(value))
    return re.sub(r"[^\W\d_]+\.?", "M", shape)


# ------------------------------------------------------------------ truncation

_FUNCTION_WORD_END_RE = re.compile(
    r"(?:\b(?:de|du|des|d['’]|la|le|les|l['’]|et|ou|à|a|au|aux|en|pour|avec|sur|dans|par|un|une|ses|son|sa|leur|leurs|"
    r"of|the|and|or|in|to|for|with|on|at|by|from)\s*|[,(]\s*)$",
    re.I,
)
# Lowercase only: "Virtual Try On, Beauty" is a product name.
_ORPHAN_RE = re.compile(
    r"\b(?:du|de\s+la|des|au|aux|sur|avec|dans|par|pour|in|of|the|with|for|to|from|via|on)\s*(?=[,)]|\s[,)])"
)


def looks_truncated(text: str) -> str | None:
    """Reason when `text` ends like a cut sentence or holds an orphan gap."""
    stripped = _collapse(text)
    if not stripped:
        return None
    if stripped.count("(") > stripped.count(")"):
        return "parenthese_ouverte"
    if _FUNCTION_WORD_END_RE.search(stripped):
        return "fin_sur_mot_outil" if not stripped.endswith(",") else "fin_sur_virgule"
    if _ORPHAN_RE.search(stripped):
        return "mot_manquant"
    return None


# ------------------------------------------------------------------ language

_EN_WORDS = frozenset("the and of to in for with on by from as is are was were this that our their within across".split())
_FR_WORDS = frozenset("le la les des du de et pour avec dans sur par une un aux au est sont été ce cette ces leur".split())


def content_language(data: dict) -> str:
    """'en' when the experiences read as English, else 'fr'."""
    words: list[str] = []
    for exp in data.get("experiences") or []:
        if not isinstance(exp, dict):
            continue
        for sec in exp.get("sections") or []:
            if isinstance(sec, dict):
                content = sec.get("content")
                for item in content if isinstance(content, list) else [content]:
                    words.extend(re.findall(r"[a-zà-ÿ]+", str(item or "").lower()))
    en = sum(1 for w in words if w in _EN_WORDS)
    fr = sum(1 for w in words if w in _FR_WORDS)
    return "en" if en >= 20 and en > 2 * fr else "fr"


# ------------------------------------------------------------------ walk

def _iter_text_fields(data: dict):
    """(path, getter, setter) for every client-visible string."""

    def field(obj, key, path):
        if isinstance(obj.get(key), str):
            yield path, obj, key

    yield from field(data, "title", "title")
    yield from field(data, "description", "description")
    for i, exp in enumerate(data.get("experiences") or []):
        if not isinstance(exp, dict):
            continue
        for key in ("date", "role", "company_highlight"):
            yield from field(exp, key, f"experiences[{i}].{key}")
        for j, sec in enumerate(exp.get("sections") or []):
            if not isinstance(sec, dict):
                continue
            yield from field(sec, "heading", f"experiences[{i}].sections[{j}].heading")
            content = sec.get("content")
            if isinstance(content, list):
                for k, item in enumerate(content):
                    if isinstance(item, str):
                        yield f"experiences[{i}].sections[{j}].content[{k}]", content, k
            elif isinstance(content, str):
                yield f"experiences[{i}].sections[{j}].content", sec, "content"
    for i, f in enumerate(data.get("formations") or []):
        if isinstance(f, dict):
            for key in ("date", "degree", "school"):
                yield from field(f, key, f"formations[{i}].{key}")
    certs = data.get("certifications") or []
    for i, c in enumerate(certs):
        if isinstance(c, str):
            yield f"certifications[{i}]", certs, i
        elif isinstance(c, dict):
            yield from field(c, "name", f"certifications[{i}].name")
    for i, lang in enumerate(data.get("languages") or []):
        if isinstance(lang, dict):
            for key in ("name", "level"):
                yield from field(lang, key, f"languages[{i}].{key}")
    for i, cat in enumerate(data.get("skills") or []):
        if not isinstance(cat, dict):
            continue
        yield from field(cat, "category", f"skills[{i}].category")
        items = cat.get("items")
        if isinstance(items, list):
            for k, item in enumerate(items):
                if isinstance(item, str):
                    yield f"skills[{i}].items[{k}]", items, k
    for i, proj in enumerate(data.get("projects") or []):
        if not isinstance(proj, dict):
            continue
        for key in ("name", "date"):
            yield from field(proj, key, f"projects[{i}].{key}")
        details = proj.get("details")
        if isinstance(details, list):
            for k, item in enumerate(details):
                if isinstance(item, str):
                    yield f"projects[{i}].details[{k}]", details, k


def client_texts(data: dict) -> list[str]:
    return [container[key] for _, container, key in _iter_text_fields(data)]


def _is_bullet_path(path: str) -> bool:
    return ".content[" in path or ".details[" in path or path.startswith("certifications[")


# ------------------------------------------------------------------ steps

def _clean_strings(out: dict, furniture: list[str], vocabulary: set[str], stats: dict) -> None:
    for path, container, key in list(_iter_text_fields(out)):
        original = container[key]
        text = original
        stripped = _strip_furniture(text, furniture)
        if _collapse(stripped) != _collapse(text):
            stats["furniture"].append(_collapse(text)[:160])
            text = stripped
        text, n_lig = repair_broken_ligatures(text)
        text, n_cap = repair_detached_capitals(text, vocabulary)
        text, n_punct = repair_missing_space_after_punctuation(text)
        if n_lig or n_cap or n_punct:
            stats["typo"].append(_collapse(original)[:160])
        if _INLINE_PLACEHOLDER_RE.search(text) or _EMPTY_PARENS_RE.search(text):
            text = _EMPTY_PARENS_RE.sub("", _INLINE_PLACEHOLDER_RE.sub("", text))
            stats["placeholder"].append(_collapse(original)[:160])
        if _is_bullet_path(path):
            unmarked = strip_bullet_marker(text)
            if unmarked != text:
                stats["bullet_marker"] += 1
                text = unmarked
            if text.rstrip().endswith(",") and not text.rstrip().endswith(",,"):
                text = text.rstrip()[:-1]
                stats["trailing_comma"] += 1
        text = text.replace("|:", " :")
        if path in ("title", "description") or path.endswith((".role", ".company_highlight")):
            text = re.sub(r"\s*\|\s*", " · ", text)
        text = _collapse(text)
        if PLACEHOLDER_RE.match(text) and text:
            stats["placeholder"].append(_collapse(original)[:160])
            text = ""
        if text != original:
            container[key] = text


_GLUED_ITEMS_RE = re.compile(r"\s+[▪•◦●■]\s+")


def _split_glued_certifications(out: dict) -> None:
    """« A ▪ B ▪ C » in one certification: three certifications; a piece
    already listed (same words) is a duplicate."""
    certs = out.get("certifications")
    if not isinstance(certs, list):
        return
    split: list = []
    for cert in certs:
        if isinstance(cert, str) and _GLUED_ITEMS_RE.search(cert):
            split.extend(strip_bullet_marker(p).strip() for p in _GLUED_ITEMS_RE.split(cert) if strip_bullet_marker(p).strip())
        else:
            split.append(cert)
    kept: list = []
    seen: list[str] = []
    for cert in split:
        key = _norm(cert.get("name") if isinstance(cert, dict) else cert)
        # Same words, or the first words of a longer one when long enough to
        # be a cut copy ("PSM I" is not a copy of "PSM II").
        if key and any(key == other or (len(key.split()) >= 4 and other.startswith(key + " ")) for other in seen):
            add_content_warning(out, "certification_duplicate_removed", f"Certification en double retirée : {cert}")
            continue
        if key:
            seen.append(key)
        kept.append(cert)
    out["certifications"] = kept


def _drop_empty(out: dict, stats: dict, name: str, title: str) -> None:
    for exp in out.get("experiences") or []:
        if not isinstance(exp, dict):
            continue
        sections = []
        for sec in exp.get("sections") or []:
            if not isinstance(sec, dict):
                sections.append(sec)
                continue
            if isinstance(sec.get("content"), list):
                sec["content"] = [c for c in sec["content"] if not (isinstance(c, str) and not c.strip())]
            if sec.get("content") or str(sec.get("heading") or "").strip():
                sections.append(sec)
        exp["sections"] = sections
    out["formations"] = [
        f for f in out.get("formations") or []
        if not isinstance(f, dict) or any(str(f.get(k) or "").strip() for k in ("date", "degree", "school"))
    ]
    out["certifications"] = [
        c for c in out.get("certifications") or []
        if not (isinstance(c, str) and not c.strip())
    ]
    out["languages"] = [
        lang for lang in out.get("languages") or []
        if not isinstance(lang, dict) or str(lang.get("name") or "").strip()
    ]
    name_key, title_key = _norm(name), _norm(title)
    skills = []
    for cat in out.get("skills") or []:
        if not isinstance(cat, dict):
            skills.append(cat)
            continue
        items = []
        for item in cat.get("items") or []:
            if isinstance(item, str):
                key = _norm(item)
                if not key:
                    continue
                if key in {name_key, title_key} and key:
                    stats["skill_removed"].append(item)
                    continue
            items.append(item)
        cat["items"] = items
        if items or not str(cat.get("category") or "").strip():
            if items:
                skills.append(cat)
        # A category left empty disappears with its last item.
    out["skills"] = skills
    for proj in out.get("projects") or []:
        if isinstance(proj, dict) and isinstance(proj.get("details"), list):
            proj["details"] = [d for d in proj["details"] if not (isinstance(d, str) and not d.strip())]


def _normalize_dates(out: dict, stats: dict) -> None:
    targets = []
    for exp in out.get("experiences") or []:
        if isinstance(exp, dict):
            targets.append(exp)
    for f in out.get("formations") or []:
        if isinstance(f, dict):
            targets.append(f)
    for proj in out.get("projects") or []:
        if isinstance(proj, dict):
            targets.append(proj)
    for obj in targets:
        value = obj.get("date")
        if not isinstance(value, str) or not value.strip():
            continue
        formatted = format_date_text(value)
        if formatted != value:
            stats["dates"].append(f"{value} -> {formatted}")
            obj["date"] = formatted


def _experience_key(exp: dict) -> tuple[str, str, str]:
    return (_norm(exp.get("date")), _norm(exp.get("role")), _norm(exp.get("company_highlight")))


def _merge_duplicate_experiences(out: dict) -> None:
    merged: list = []
    for exp in out.get("experiences") or []:
        previous = merged[-1] if merged else None
        if (
            isinstance(exp, dict) and isinstance(previous, dict)
            and _experience_key(exp) == _experience_key(previous) and any(_experience_key(exp))
        ):
            existing = previous.setdefault("sections", [])
            for sec in exp.get("sections") or []:
                if sec not in existing:
                    existing.append(sec)
            add_content_warning(
                out, "duplicate_experience_merged",
                f"En-tête d'expérience répété fusionné : {exp.get('date', '')} {exp.get('role', '')} — {exp.get('company_highlight', '')}".strip(),
            )
            continue
        merged.append(exp)
    out["experiences"] = merged


_COMPANY_SPLIT_RE = re.compile(r"\s+(?:\||—|–|·)\s+")


def _lowercase_words(text: str) -> int:
    return sum(1 for w in re.findall(r"[^\W\d_][\w'’-]*", text) if w[:1].islower())


def company_sentence(company: str) -> bool:
    """A sentence (context, mission summary) rather than a company name:
    several lowercase words, not "GROUPE CREDIT MUTUEL CIC – EURO INFORMATION"."""
    company = _collapse(company)
    return len(company.split()) > 8 and _lowercase_words(company) >= 4


def _split_company_sentences(out: dict) -> None:
    for exp in out.get("experiences") or []:
        if not isinstance(exp, dict):
            continue
        company = _collapse(exp.get("company_highlight"))
        if not company or not company_sentence(company):
            continue
        match = _COMPANY_SPLIT_RE.search(company)
        if not match:
            continue
        head, tail = company[: match.start()].strip(" ,;"), company[match.end():].strip(" ,;")
        if not head or len(head.split()) > 10 or len(tail.split()) < 3 or _lowercase_words(tail) < 2:
            continue
        exp["company_highlight"] = head
        sections = exp.setdefault("sections", [])
        context = next(
            (s for s in sections if isinstance(s, dict) and _norm(s.get("heading")) in {"contexte", "context"}),
            None,
        )
        if context is None:
            sections.insert(0, {"heading": "Contexte", "content": [tail]})
        else:
            content = context.get("content")
            if isinstance(content, list):
                if tail not in content:
                    content.insert(0, tail)
            else:
                context["content"] = [tail] + ([content] if content else [])
        add_content_warning(
            out, "company_sentence_split",
            f"Champ entreprise « {company} » : « {head} » gardé, « {tail} » placé en Contexte.",
            company=head,
        )


def _sort_experiences(out: dict) -> None:
    exps = [e for e in out.get("experiences") or [] if isinstance(e, dict)]
    if len(exps) < 2 or len(exps) != len(out.get("experiences") or []):
        return
    keys = [date_sort_key(str(e.get("date") or "")) for e in exps]
    if keys[0] is not None and keys[0][0] == keys[0][1]:
        # "04/2025" alone heading the list, with the latest start of all: the
        # source lists it first as the current position, not as a past month.
        parsed = parse_date_text(str(exps[0].get("date") or ""))
        if parsed and parsed["end"] is None and all(k is None or k[1] <= keys[0][1] for k in keys[1:]):
            keys[0] = ((9999, 12), keys[0][1])
    if any(k is None for k in keys):
        readable = [k for k in keys if k is not None]
        if readable != sorted(readable, reverse=True):
            unreadable = [str(e.get("date") or "(vide)") for e, k in zip(exps, keys) if k is None]
            add_content_warning(
                out, "experience_order_unverified",
                "Ordre des expériences non vérifié : date(s) illisible(s) " + ", ".join(unreadable[:5]),
            )
        return
    order = sorted(range(len(exps)), key=lambda i: keys[i], reverse=True)
    if order == list(range(len(exps))):
        return
    out["experiences"] = [exps[i] for i in order]
    add_content_warning(
        out, "experiences_reordered",
        "Expériences remises dans l'ordre antichronologique : "
        + " ; ".join(str(exps[i].get("date") or "") for i in order[:12]),
    )


# ------------------------------------------------------------------ source repairs

def _source_index(source_text: str) -> str:
    return re.sub(r"[ \t]+", " ", source_text or "")


def _words_regex(text: str) -> str:
    return r"\s+".join(re.escape(w) for w in text.split())


def _tokens(text: str) -> list[str]:
    """Words and bullet marks: spacing and punctuation ignored ("volumétrie :"
    and "volumétrie:" match), a bullet between two lines is kept."""
    return re.findall(r"[0-9a-zà-ÿ+#]+|[•▪◦●■➢✓]", unicodedata.normalize("NFKC", str(text or "")).lower())


WRAPPED_LINE_MIN_CHARS = 70


def _rejoin_split_bullets(content: list, source_tokens: str) -> tuple[list, int]:
    out: list = []
    joined = 0
    for item in content:
        if out and isinstance(item, str) and isinstance(out[-1], str) and item.strip():
            previous = out[-1]
            cut = looks_truncated(previous) in {"fin_sur_mot_outil", "fin_sur_virgule", "parenthese_ouverte"}
            # Without a cut end, only a long line can be a wrapped one: two
            # short cells of a table ("Office 365" / "entre 15 et 25 …")
            # stay apart.
            wrapped = len(previous) >= WRAPPED_LINE_MIN_CHARS and not previous.rstrip().endswith((".", "!", "?", ";", ":"))
            if cut or (wrapped and (item.lstrip()[:1].islower() or item.lstrip().startswith("("))):
                probe = " ".join(_tokens(previous)[-6:] + _tokens(item)[:6])
                if probe and f" {probe} " in source_tokens:
                    glue = "" if previous.rstrip().endswith("(") else " "
                    out[-1] = f"{previous.rstrip()}{glue}{item.strip()}"
                    joined += 1
                    continue
        out.append(item)
    return out, joined


CONTINUATION_MAX_WORDS = 25


def _complete_from_source(text: str, source: str, vocabulary: set[str], siblings: str = "") -> tuple[str, str | None]:
    """(text, kind) with the cut end restored from the source."""
    stripped = text.rstrip()
    reason = looks_truncated(stripped)
    words = stripped.split()
    if len(words) < 3:
        return text, None
    tail = " ".join(words[-8:])
    # 1. Mot coupé : « Souscripti » -> « Souscription ».
    last = re.findall(r"[^\W\d_]+$", stripped)
    if last and len(last[0]) >= 4 and last[0].lower() not in vocabulary:
        found = {m.group(1) for m in re.finditer(_words_regex(tail) + r"([^\W\d_]{2,})", source)}
        if len(found) == 1:
            return stripped + found.pop(), "word"
    # 2. Fin de phrase perdue, sur la ligne suivante (« erreurs et » +
    # « disponibilité ») ou sur la même ligne (« SMS et » + « e-mail »).
    if reason in {"fin_sur_mot_outil", "parenthese_ouverte"}:
        found = {
            m.group(1).strip()
            for m in re.finditer(
                _words_regex(tail) + r"(?:[ \t]*\n[ \t]*|[ \t]+)([a-zà-ÿ(][^\n]{0,200})(?:\n|$)", source
            )
        }
        # A list introduction whose colon was dropped: « principalement sur : ».
        colon = {m.group(1) for m in re.finditer(_words_regex(tail) + r"[ \t]*([:…])[ \t]*(?:\n|$)", source)}
        if not found and len(colon) == 1:
            return f"{stripped} {colon.pop()}", "line"
        if len(found) == 1:
            continuation = found.pop()
            # The next source line starts in lowercase after a cut sentence:
            # it is its end, unless the model kept it elsewhere.
            if len(continuation.split()) <= CONTINUATION_MAX_WORDS and _norm(continuation) not in siblings:
                return f"{stripped} {continuation}", "line"
    return text, None


def _fill_gaps_from_source(text: str, source: str) -> tuple[str, int]:
    filled = 0
    for _ in range(3):
        match = _ORPHAN_RE.search(text)
        if not match:
            break
        left_words = text[: match.end()].split()[-4:]
        right = text[match.end():].lstrip()
        right_words = right.split()[:3]
        if not left_words or not right_words:
            break
        pattern = _words_regex(" ".join(left_words)) + r"\s+([^\n]{1,40}?)\s*" + _words_regex(" ".join(right_words))
        found = {m.group(1).strip() for m in re.finditer(pattern, source)}
        if len(found) != 1:
            break
        gap = found.pop()
        if not gap or len(gap.split()) > 4:
            break
        text = f"{text[: match.end()].rstrip()} {gap}{'' if right.startswith((',', ')')) else ' '}{right}"
        filled += 1
    return text, filled


def _repair_from_source(out: dict, source_text: str, vocabulary: set[str]) -> None:
    source = _source_index(source_text)
    if not source.strip():
        return
    source_tokens = " " + " ".join(_tokens(source_text)) + " "
    for exp in out.get("experiences") or []:
        if not isinstance(exp, dict):
            continue
        for key in ("role", "company_highlight"):
            value = exp.get(key)
            if isinstance(value, str) and value.strip():
                fixed, kind = _complete_from_source(value, source, vocabulary)
                if kind == "word":
                    exp[key] = fixed
                    add_content_warning(out, "word_completed_from_source", f"Mot coupé complété : « {value} » -> « {fixed} »")
        for sec in exp.get("sections") or []:
            if not isinstance(sec, dict) or not isinstance(sec.get("content"), list):
                continue
            content, joined = _rejoin_split_bullets(sec["content"], source_tokens)
            if joined:
                add_content_warning(
                    out, "bullet_rejoined",
                    f"{joined} puce(s) coupée(s) en deux recollée(s) ({exp.get('company_highlight') or exp.get('role') or ''})",
                )
            for index, item in enumerate(content):
                if not isinstance(item, str):
                    continue
                fixed, gaps = _fill_gaps_from_source(item, source)
                if gaps:
                    add_content_warning(out, "gap_filled_from_source", f"Mot manquant rétabli : « {item} » -> « {fixed} »")
                    item = fixed
                siblings = " ".join(_norm(other) for j, other in enumerate(content) if j != index and isinstance(other, str))
                fixed, kind = _complete_from_source(item, source, vocabulary, siblings)
                if kind:
                    add_content_warning(
                        out, "word_completed_from_source",
                        f"Fin de texte rétablie depuis le CV source : « {item} » -> « {fixed} »",
                    )
                    item = fixed
                content[index] = item
            sec["content"] = content


# ------------------------------------------------------------------ entry point

def finalize_cv_content(
    data: dict,
    source_text: str = "",
    *,
    furniture_lines: Iterable[str] = (),
    candidate_name: str | None = None,
) -> dict:
    """Return a finished copy of `data` (see module docstring)."""
    if not isinstance(data, dict):
        return data
    out = deepcopy(data)
    furniture = [_collapse(line) for line in furniture_lines if _collapse(line)]
    name = candidate_name or str(out.get("name") or "")
    # Remove "Prénom · Titre" headers copied from the source page header.
    title = str(out.get("title") or "")
    if name and title:
        furniture.append(f"{name} · {title}")
    vocabulary = text_vocabulary([source_text, *client_texts(out)])
    stats: dict[str, Any] = {
        "furniture": [], "typo": [], "placeholder": [], "dates": [], "skill_removed": [],
        "bullet_marker": 0, "trailing_comma": 0,
    }
    _split_glued_certifications(out)
    _clean_strings(out, furniture, vocabulary, stats)
    _drop_empty(out, stats, name, title)
    _repair_from_source(out, source_text, text_vocabulary([source_text]))
    _normalize_dates(out, stats)
    _merge_duplicate_experiences(out)
    _split_company_sentences(out)
    _sort_experiences(out)

    if stats["placeholder"]:
        add_content_warning(
            out, "placeholder_removed",
            f"{len(stats['placeholder'])} valeur(s) vide(s) ou « Non spécifié » retirée(s)",
            items=stats["placeholder"][:20],
        )
    if stats["furniture"]:
        add_content_warning(
            out, "page_furniture_removed",
            f"{len(stats['furniture'])} reste(s) d'en-tête/pied de page du CV source retiré(s)",
            items=stats["furniture"][:20],
        )
    if stats["skill_removed"]:
        add_content_warning(
            out, "skill_item_removed",
            "Retiré des compétences (prénom ou titre recopié) : " + ", ".join(stats["skill_removed"][:10]),
            items=stats["skill_removed"][:20],
        )
    if stats["typo"]:
        add_content_warning(
            out, "text_repaired",
            f"{len(stats['typo'])} texte(s) réparé(s) (ligature, lettre détachée, ponctuation)",
            items=stats["typo"][:20],
        )
    if stats["dates"]:
        add_content_warning(
            out, "date_normalized",
            f"{len(stats['dates'])} date(s) mise(s) au format commun",
            items=stats["dates"][:30],
        )
    return out


# ------------------------------------------------------------------ detections (QA)

def find_truncated_texts(data: dict) -> list[dict[str, str]]:
    found = []
    for path, container, key in _iter_text_fields(data):
        if path.startswith(("skills[", "languages[", "formations[")) or path.endswith(
            (".date", ".heading", "category", ".role", ".company_highlight", ".name")
        ):
            continue
        reason = looks_truncated(container[key])
        if reason == "fin_sur_virgule" and not _is_bullet_path(path):
            continue
        if reason:
            found.append({"path": path, "text": _collapse(container[key])[:200], "reason": reason})
    return found


def find_placeholders(data: dict) -> list[str]:
    found = []
    for path, container, key in _iter_text_fields(data):
        value = container[key]
        if (value.strip() and PLACEHOLDER_RE.match(value)) or _INLINE_PLACEHOLDER_RE.search(value) or _EMPTY_PARENS_RE.search(value):
            found.append(f"{path}: {value[:80]}")
    return found


def find_future_dates(data: dict, today: date | None = None) -> list[dict[str, str]]:
    today = today or date.today()
    now = (today.year, today.month)
    found = []
    for exp in data.get("experiences") or []:
        if not isinstance(exp, dict):
            continue
        parsed = parse_date_text(str(exp.get("date") or ""))
        if not parsed:
            continue
        start, end = parsed["start"], parsed["end"]
        if end is not None and not end.present and end.key(False) > now:
            found.append({"date": exp.get("date"), "role": exp.get("role"), "kind": "fin_future"})
        elif start.key(False) > now:
            found.append({"date": exp.get("date"), "role": exp.get("role"), "kind": "debut_futur"})
    return found


def experiences_out_of_order(data: dict) -> bool:
    keys = [date_sort_key(str(e.get("date") or "")) for e in data.get("experiences") or [] if isinstance(e, dict)]
    readable = [k for k in keys if k is not None]
    return readable != sorted(readable, reverse=True)


def find_page_furniture_in_content(data: dict) -> list[str]:
    found = []
    for path, container, key in _iter_text_fields(data):
        value = container[key]
        if _PAGE_MARKER_RE.search(value) or _LETTER_SPACED_RE.search(value):
            found.append(f"{path}: {value[:80]}")
    return found


def find_broken_typography(data: dict) -> list[str]:
    from .text_repair import find_detached_capitals, find_missing_space_after_punctuation

    texts = client_texts(data)
    vocabulary = text_vocabulary(texts)
    found = []
    for text in texts:
        found.extend(find_broken_ligatures(text))
        found.extend(find_detached_capitals(text, vocabulary))
        found.extend(find_missing_space_after_punctuation(text))
    return found


def content_qa_warnings(data: dict | None, today: date | None = None) -> list[dict[str, Any]]:
    """Avertissements QA tirés du JSON rendu (rien n'est modifié)."""
    if not isinstance(data, dict):
        return []
    warnings: list[dict[str, Any]] = []
    truncated = find_truncated_texts(data)
    if truncated:
        warnings.append({
            "code": "truncated_text",
            "message": f"{len(truncated)} texte(s) semblent tronqués (fin sur un mot-outil, une virgule, une parenthèse ouverte ou un mot manquant).",
            "items": truncated[:30],
        })
    future = find_future_dates(data, today)
    if future:
        warnings.append({
            "code": "future_end_date",
            "message": "Date(s) dans le futur, à confirmer avec le candidat : "
            + " ; ".join(f"{f['date']} ({f['role']})" for f in future[:6]),
            "items": future,
        })
    companies = [
        str(e.get("company_highlight")) for e in data.get("experiences") or []
        if isinstance(e, dict) and e.get("company_highlight") and company_sentence(str(e.get("company_highlight")))
    ]
    if companies:
        warnings.append({
            "code": "company_field_sentence",
            "message": "Champ entreprise rempli par une phrase : " + " ; ".join(c[:90] for c in companies[:4]),
            "items": companies,
        })
    description = _collapse(data.get("description"))
    if description and len(description.split()) < 8:
        warnings.append({
            "code": "description_too_short",
            "message": f"Description très courte ({len(description.split())} mots) : « {description} ».",
        })
    if content_language(data) == "en":
        warnings.append({
            "code": "content_language_not_french",
            "message": "Le contenu du CV est en anglais (non traduit, titres du gabarit en français) : à valider avec le client.",
        })
    typo = find_broken_typography(data)
    if typo:
        warnings.append({
            "code": "broken_ligature",
            "message": f"{len(typo)} mot(s) à la typographie cassée : " + ", ".join(typo[:8]),
            "items": typo[:30],
        })
    return warnings
