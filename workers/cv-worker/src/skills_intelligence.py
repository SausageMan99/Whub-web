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


@dataclass(frozen=True)
class ParsedSourceSkills:
    skills_by_category: dict[str, list[str]] = field(default_factory=dict)
    languages: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Section isolation
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Hellowork `➢` bullet split
# ---------------------------------------------------------------------------

_ARROW_RE = re.compile(r"^[➢>•\-–—]+\s*(.*)$")


_SPOKEN_LANGUAGE_INLINE_RE = re.compile(
    r"^(?P<head>.*?[\s,])(?P<name>"
    r"fran[çc]ais|anglais|espagnol|allemand|italien|portugais|arabe|russe|chinois|japonais|"
    r"mandarin|coreen|coréen|neerlandais|néerlandais|suedois|suédois|polonais|"
    r"tcheque|tchèque|hongrois|roumain|bulgare|grec|turc|hindi|vietnamien|"
    r"indonesien|indonésien|ukrainien|catalan|croate|slovaque|estonien|"
    r"letton|lituanien|breton|occitan|corse|basque"
    r")\s*(?P<level>(?:lu|parl[ée]|écrit|courant|bilingue|natif|native|maternel|maternelle|professionnel|technique|scolaire|notions|a1|a2|b1|b2|c1|c2)[^\n]*)$",
    re.IGNORECASE,
)


def _flush_skill_item(buffer: list[str]) -> list[str]:
    """Return one or more item strings from a buffer.

    If the buffer is multi-line and a spoken language suffix is appended
    to a real skill (e.g. "... Windows / Anglais Lu, parlé, écrit"), split
    the language off as its own item so `_split_languages_from_items` can
    hoist it. A single-line buffer that *starts with* a language name is
    returned intact so the level is preserved.
    """
    text = " ".join(part.strip() for part in buffer if part and part.strip())
    text = re.sub(r"\s+", " ", text).strip(" :;•➢-–—")
    if not text:
        return []
    match = _SPOKEN_LANGUAGE_INLINE_RE.match(text)
    if not match:
        return [text]
    head = match.group("head").strip(" ,")
    name = match.group("name").strip()
    level = match.group("level").strip()
    if not head and len([part for part in buffer if part and part.strip()]) == 1:
        return [text]
    if not head:
        return [f"{name} {level}".strip()]
    return [head, f"{name} {level}".strip()]


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
        items.extend(_flush_skill_item(buffer))
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


# ---------------------------------------------------------------------------
# Label normalisation
# ---------------------------------------------------------------------------

_NORMALIZED_SKILL_LABELS: dict[str, str] = {
    "azure": "Azure",
    "aws": "AWS",
    "gcp": "GCP",
    "gitlab cicd": "GitLab CI/CD",
    "gitlab ci/cd": "GitLab CI/CD",
    "gitlab ci cd": "GitLab CI/CD",
    "docker-compose": "Docker Compose",
    "docker compose": "Docker Compose",
    "sqlserver": "SQL Server",
    "sql server": "SQL Server",
    "postegresql": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "graphana": "Grafana",
    "grafana": "Grafana",
    "elasticsearch": "Elasticsearch",
    "logstash": "LogStash",
    "kibana": "Kibana",
    "dynatrace": "Dynatrace",
    "redis": "Redis",
    "tomcat": "Tomcat",
    "spring boot": "Spring Boot",
    "spring": "Spring",
    "hibernate": "Hibernate",
    "jwt": "JWT",
    "oauth2": "OAuth2",
    "oauth 2": "OAuth2",
    "ldap": "LDAP",
    "x509": "X509",
    "openssl": "OpenSSL",
    "openssh": "OpenSSH",
    "pkcs7": "PKCS7",
    "owasp": "OWASP",
    "ubuntu": "Ubuntu",
    "centos": "CentOS",
    "aix": "AIX",
    "windows": "Windows",
    "linux": "Linux",
    "macos": "macOS",
    "ios": "iOS",
    "android": "Android",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "node js": "Node.js",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "angularjs": "AngularJS",
    "websocket": "WebSocket",
    "html5": "HTML5",
    "css3": "CSS3",
    "groovy": "Groovy",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "c++": "C++",
    "c#": "C#",
    "f#": "F#",
    "toad": "TOAD",
}


def _fold_label(value: str) -> str:
    cleaned = unicodedata.normalize("NFKD", value or "")
    cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", cleaned.casefold()).strip()


def _normalise_skill_label(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip(" .,;:()[]{}•➢")
    if not cleaned:
        return ""
    folded = _fold_label(cleaned)
    if folded in _NORMALIZED_SKILL_LABELS:
        return _NORMALIZED_SKILL_LABELS[folded]
    return cleaned


def _split_skill_values(value: str) -> list[str]:
    parts = re.split(r",|;|\s+\/\s+", value or "")
    out: list[str] = []
    for part in parts:
        label = _normalise_skill_label(part)
        if label and label not in out:
            out.append(label)
    return out


# ---------------------------------------------------------------------------
# Source prefix → category mapping
# ---------------------------------------------------------------------------

_PREFIX_CATEGORY_MAP: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?:cloud|devops)\b", re.IGNORECASE), "Cloud & DevOps"),
    (re.compile(r"^s[ée]curit[ée]\b", re.IGNORECASE), "Sécurité"),
    (re.compile(r"^(?:data\s*bases?|bases?\s+de\s+donn[ée]es?)\b", re.IGNORECASE), "Bases de données"),
    (re.compile(r"^syst[èe]mes?\b", re.IGNORECASE), "Systèmes & Environnements"),
    (re.compile(r"^observabilit[ée]\b|^apm\b", re.IGNORECASE), "Observabilité"),
    (re.compile(r"^architecture\s+logicielle\b|^architecture\b", re.IGNORECASE), "Architecture & Conception"),
)


def _category_from_prefixed_item(item: str) -> tuple[str | None, str]:
    match = re.match(r"^([^:：]{3,80})\s*[:：]\s*(.+)$", item)
    if not match:
        return None, item
    prefix = match.group(1).strip()
    rest = match.group(2).strip()
    for pattern, category in _PREFIX_CATEGORY_MAP:
        if pattern.search(prefix):
            return category, rest
    return None, item


# ---------------------------------------------------------------------------
# Fallback keyword classification
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Architecture & Conception",
        (
            "architecture", "urbanisation", "référentiel", "referentiel",
            "soa", "eda", "eip", "paas", "iaas", "caas",
            "stream-processing", "asynchrone", "conception",
        ),
    ),
    (
        "Cloud & DevOps",
        (
            "aws", "azure", "gcp", "docker", "kubernetes", "openshift",
            "jenkins", "gitlab", "nexus", "devops", "ci/cd", "cicd",
        ),
    ),
    (
        "Observabilité",
        (
            "dynatrace", "elastic", "logstash", "kibana", "grafana", "graphana",
            "beats", "apm", "sla", "slo",
        ),
    ),
    (
        "Sécurité",
        (
            "jwt", "oauth", "jaas", "loginmodule", "ldap", "x509", "openssl",
            "pkcs", "owasp", "authentification", "signature", "non-répudiation",
            "non repudiation",
        ),
    ),
    (
        "Bases de données",
        (
            "sql", "mysql", "postgres", "oracle", "mongodb", "sybase",
            "db2", "mariadb", "hibernate",
        ),
    ),
    (
        "Langages & Frameworks",
        (
            "java", "spring", "php", "c#", "node", "typescript",
            "jni", "jdbc", "groovy", "angular", "html5", "websocket",
            "react", "vue", "next",
        ),
    ),
    (
        "Méthodologies",
        (
            "togaf", "c4", "ddd", "safe", "scrum", "agile", "roadmap",
            "audit", "directeur", "direction d'équipe",
        ),
    ),
    (
        "Systèmes & Environnements",
        (
            "linux", "rhel", "aix", "centos", "ubuntu", "windows",
        ),
    ),
)


def _category_for_skill_value(value: str) -> str:
    lower = _fold_label(value)
    for category, keywords in _CATEGORY_KEYWORDS:
        for keyword in keywords:
            folded_keyword = _fold_label(keyword)
            if folded_keyword in lower:
                return category
    return "Outils & Environnements"


# ---------------------------------------------------------------------------
# Spoken language hoisting
# ---------------------------------------------------------------------------

_SPOKEN_LANGUAGE_HEADING_RE = re.compile(
    r"^\s*(?:fran[çc]ais|anglais|espagnol|allemand|italien|portugais|arabe|russe|chinois|japonais|mandarin|coreen|coréen|neerlandais|néerlandais|suedois|suédois|polonais|tcheque|tchèque|hongrois|roumain|bulgare|grec|turc|hindi|vietnamien|indonesien|indonésien|ukrainien|catalan|croate|slovaque|estonien|letton|lituanien|breton|occitan|corse|basque)\b",
    re.IGNORECASE,
)
_LANGUAGE_LEVEL_KEYWORDS_RAW = (
    "lu", "parlé", "parle", "écrit", "ecrit", "courant", "bilingue",
    "natif", "native", "maternel", "maternelle", "professionnel",
    "technique", "scolaire", "notions",
)
_LANGUAGE_LEVEL_KEYWORDS_FOLDED = {_fold_label(keyword) for keyword in _LANGUAGE_LEVEL_KEYWORDS_RAW}
_LANGUAGE_CECRL = {"a1", "a2", "b1", "b2", "c1", "c2"}
_LANGUAGE_INLINE_NAME_RE = re.compile(
    r"(?:fran[çc]ais|anglais|espagnol|allemand|italien|portugais|arabe|russe|chinois|japonais|"
    r"mandarin|coreen|coréen|neerlandais|néerlandais|suedois|suédois|polonais|"
    r"tcheque|tchèque|hongrois|roumain|bulgare|grec|turc|hindi|vietnamien|"
    r"indonesien|indonésien|ukrainien|catalan|croate|slovaque|estonien|"
    r"letton|lituanien|breton|occitan|corse|basque)",
    re.IGNORECASE,
)


def _split_languages_from_items(items: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Remove spoken-language lines from a list of skill items.

    A spoken-language line is one that starts with a known language name.
    The level (`Lu, parlé, écrit`, `A2`, `courant`, ...) can be on the same
    line, on a following line, or split across multiple following lines.
    """
    remaining: list[str] = []
    languages: list[dict[str, str]] = []
    index = 0
    while index < len(items):
        item = items[index].strip()
        if not _SPOKEN_LANGUAGE_HEADING_RE.match(item):
            remaining.append(item)
            index += 1
            continue
        name_match = _LANGUAGE_INLINE_NAME_RE.search(item)
        assert name_match is not None
        name = name_match.group(0).strip()
        name = name[:1].upper() + name[1:].lower()
        tail = item[name_match.end():].strip(" ,;:.-–—")
        level_parts: list[str] = []
        if tail and (
            any(kw in _fold_label(tail) for kw in _LANGUAGE_LEVEL_KEYWORDS_FOLDED)
            or _fold_label(tail) in _LANGUAGE_CECRL
            or "," in tail
        ):
            level_parts.append(tail)
        index += 1
        while index < len(items):
            nxt = items[index].strip()
            if not nxt:
                break
            if _SPOKEN_LANGUAGE_HEADING_RE.match(nxt):
                break
            folded_nxt = _fold_label(nxt)
            if (
                any(kw in folded_nxt for kw in _LANGUAGE_LEVEL_KEYWORDS_FOLDED)
                or folded_nxt in _LANGUAGE_CECRL
                or "," in nxt
            ):
                level_parts.append(nxt)
                index += 1
                continue
            break
        level = ", ".join(part for part in level_parts if part).strip()
        languages.append({"name": name, "level": level})
    return remaining, languages


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_source_skills_section(source_text: str) -> ParsedSourceSkills:
    """Parse the `COMPÉTENCES` section of a source CV.

    Returns a deterministic, deduplicated, taxonomy-aligned view. Empty input
    or absent `COMPÉTENCES` heading yields an empty result.
    """
    lines = _extract_skills_lines(source_text)
    items = _split_arrow_skill_items(lines)
    items, languages = _split_languages_from_items(items)
    grouped: dict[str, list[str]] = {}

    for item in items:
        category, rest = _category_from_prefixed_item(item)
        if category:
            for value in _split_skill_values(rest):
                grouped.setdefault(category, [])
                if value not in grouped[category]:
                    grouped[category].append(value)
            continue
        for value in _split_skill_values(item):
            target = _category_for_skill_value(value)
            grouped.setdefault(target, [])
            if value not in grouped[target]:
                grouped[target].append(value)

    return ParsedSourceSkills(skills_by_category=grouped, languages=languages)


# ---------------------------------------------------------------------------
# Display-layer dedup / normalisation
# ---------------------------------------------------------------------------

_CATEGORY_PRIORITY: dict[str, int] = {
    "Architecture & Conception": 1,
    "Cloud & DevOps": 2,
    "Sécurité": 3,
    "Observabilité": 4,
    "Langages & Frameworks": 5,
    "Backend": 5,
    "Frontend": 6,
    "Bases de données": 7,
    "Data & BI": 7,
    "Méthodologies": 8,
    "Systèmes & Environnements": 9,
    "Outils & Environnements": 10,
    "Autres": 99,
}


_CATEGORY_ALIASES: dict[str, str] = {
    "Cloud / DevOps": "Cloud & DevOps",
    "Data": "Bases de données",
    "Outils & méthodes": "Méthodologies",
    "Frameworks & Librairies": "Langages & Frameworks",
    "Outils & méthodes ": "Méthodologies",
}


def _normalise_category(category: str) -> str:
    normalized = re.sub(r"\s+", " ", category or "").strip()
    normalized = re.sub(r"\s*[—-]\s*suite(?:\s+\d+)?$", "", normalized, flags=re.IGNORECASE).strip()
    if normalized in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[normalized]
    return normalized or "Outils & Environnements"


def normalise_skill_key(value: str) -> str:
    """Canonical key used for global deduplication."""
    cleaned = unicodedata.normalize("NFKD", value or "")
    cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    folded = cleaned.casefold()
    folded = re.sub(r"\s+", "", folded)
    folded = folded.replace("cicd", "cicd")
    aliases = {
        "sqlserver": "sqlserver",
        "postgresql": "postgresql",
        "postegresql": "postgresql",
        "dockercompose": "dockercompose",
        "dockercompose": "dockercompose",
        "gitlabcicd": "gitlabcicd",
        "graphana": "grafana",
    }
    cleaned_folded = re.sub(r"[^a-z0-9+#.]+", "", folded)
    return aliases.get(cleaned_folded, cleaned_folded)


def build_display_skills(
    raw_skills: list[dict],
    source_text: str = "",
) -> list[dict]:
    """Deduplicate a skills list across categories and normalize labels.

    The result preserves the W hub taxonomy. Items that land in `Autres` are
    reclassified by `_category_for_skill_value` so that the public
    `Autres` bucket should normally stay empty.
    """
    grouped: dict[str, list[str]] = {}
    seen: set[str] = set()
    candidates: list[tuple[int, str, str]] = []

    for skill in raw_skills or []:
        if not isinstance(skill, dict):
            continue
        category = _normalise_category(str(skill.get("category") or ""))
        for item in skill.get("items") or []:
            label = _normalise_skill_label(str(item))
            if not label:
                continue
            target = _category_for_skill_value(label) if category == "Autres" else category
            if not target:
                target = "Outils & Environnements"
            priority = _CATEGORY_PRIORITY.get(target, 50)
            candidates.append((priority, target, label))

    for _, category, label in sorted(candidates, key=lambda row: (row[0], row[1], row[2].casefold())):
        key = normalise_skill_key(label)
        if not key or key in seen:
            continue
        seen.add(key)
        grouped.setdefault(category, []).append(label)

    return [{"category": category, "items": items} for category, items in grouped.items() if items]
