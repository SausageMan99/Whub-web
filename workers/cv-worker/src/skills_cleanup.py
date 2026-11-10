"""Passe déterministe de nettoyage de la section « Compétences techniques ».

Appliquée après le modèle (et après l'override visuel des compétences) comme
garde-fou : la section `skills` ne doit contenir que des compétences, rangées
dans peu de catégories, sans doublon ni titre répété.

Ce qui n'est pas une compétence est rangé à sa place ou retiré, jamais en
silence :
- formation / diplôme / école -> `formations` (supprimé si déjà présent) ;
- langue parlée -> `languages` (idem) ;
- certification -> `certifications` (idem) ;
- soft skill -> supprimé (la section est technique) ;
- texte de mission (dates, société d'une expérience, verbe d'action, phrase
  longue) -> supprimé s'il figure déjà dans les expériences, sinon déplacé
  dans `projects` quand il vient d'une catégorie Projets/Réalisations, sinon
  conservé (rien de réel ne disparaît) ;
- doublons (casse, accents, ponctuation) -> supprimés ;
- parenthèses ouvertes par une découpe sur les virgules -> recollées, sinon
  réparées ;
- catégories « X (suite) », « X — suite 2 » -> fusionnées ; « Autres » unique,
  vidé autant que possible vers les catégories du CV d'origine.

Chaque action est journalisée et ajoutée à `data["_skills_cleanup"]` (liste
d'entrées {action, item, category, target}) ; le worker en fait un
avertissement QA.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from copy import deepcopy
from typing import Any

from .skills_intelligence import _category_for_skill_value, _extract_skills_lines

log = logging.getLogger(__name__)

CLEANUP_REPORT_KEY = "_skills_cleanup"
MAX_ITEMS_PER_CATEGORY = 12
MAX_CATEGORIES = 8
MAX_SKILL_WORDS = 8
MAX_SKILL_CHARS = 90


# --------------------------------------------------------------------------- normalisation

def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    folded = without_accents.lower().replace("’", "'")
    folded = re.sub(r"[^a-z0-9+#]+", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


def skill_key(text: str) -> str:
    """Clé de dédoublonnage : casse, accents, espaces et ponctuation ignorés."""
    return _fold(text).replace(" ", "")


_STOPWORDS = {
    "les", "des", "une", "pour", "avec", "dans", "sur", "par", "aux", "est", "son", "ses", "leur",
    "and", "the", "for", "with", "via", "chez", "tout", "tous", "mise", "place",
}


def _tokens(text: str) -> list[str]:
    return [t for t in _fold(text).split() if len(t) >= 3 and t not in _STOPWORDS and not t.isdigit()]


def _coverage(item: str, haystack_folded: str) -> float:
    tokens = _tokens(item)
    if not tokens:
        return 1.0
    words = set(haystack_folded.split())
    return sum(1 for t in tokens if t in words) / len(tokens)


def _clean_text(text: str) -> str:
    text = str(text or "").replace("‌", "").replace("​", "").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(" |•·▪➢✓-–—,;:\t")
    return text.strip()


# --------------------------------------------------------------------------- détecteurs

_MONTHS = r"(?:janv(?:ier)?|f[ée]v(?:rier)?|mars|avr(?:il)?|mai|juin|juil(?:let)?|ao[ûu]t|sept?(?:embre)?|oct(?:obre)?|nov(?:embre)?|d[ée]c(?:embre)?|january|february|march|april|may|june|july|august|september|october|november|december)\.?"
_DATE_RE = re.compile(
    rf"\b{_MONTHS}\s*[-/ ]?\s*(?:19|20)\d{{2}}\b"            # Juin 2022, juin-2022
    r"|\b(?:0?[1-9]|1[0-2])\s*/\s*(?:19|20)\d{2}\b"            # 01/2022
    r"|\bdepuis\s+(?:19|20)\d{2}\b"
    r"|\b(?:19|20)\d{2}\s*[-–—/àa]+\s*(?:aujourd|pr[ée]sent|present|ce jour)",
    re.I,
)
# « 2017-2019 » : date de mission en tête d'item ou dans une phrase ; après un
# produit (« Windows Server 2000-2022 », « SCOM 2007/2012 ») c'est une version.
_YEAR_RANGE_RE = re.compile(r"\b(?:19|20)\d{2}\s*[-–—/]+\s*(?:19|20)\d{2}\b")
_EDUCATION_RE = re.compile(
    r"baccalaur[ée]at|\bbac\b|\bbts\b|\bdut\b|\bdeug\b|\bdess\b|\bdea\b|\bdest\b|doctorat|\bph\.?d\b|classe pr[ée]paratoire"
    r"|grandes? [ée]coles?|business school|universit[ée]|\biut\b|dipl[oô]m[ée]s?\b|\bcursus\b|lyc[ée]e|mast[eè]re|\bmba\b"
    r"|\bmaster\s+(?:\d|[12]\b|of|en|de|d['’]|management|informatique|professionnel|recherche|sciences|grande|miage)"
    r"|\blicence\s+(?:pro\b|professionnelle|en|de|d['’]|informatique|histoire|sciences|miage|lmd|math)"
    r"|ing[ée]nieur\s+dipl[oô]m|[ée]cole\s+(?:d['’]|de|des|nationale|sup[ée]rieure|polytechnique|centrale|normale|d'ing)"
    r"|\bscolarit[ée]\b",
    re.I,
)
# Mots en capitales seulement (titres de section du CV source).
_EDUCATION_UPPER_RE = re.compile(r"\b(?:EDUCATION|ETUDES|ÉTUDES|FORMATIONS?|DIPL[OÔ]MES?)\b")
_LANGUAGE_NAMES = (
    "français", "francais", "anglais", "espagnol", "allemand", "italien", "portugais", "arabe", "russe", "chinois",
    "mandarin", "japonais", "coréen", "coreen", "néerlandais", "neerlandais", "suédois", "suedois", "polonais",
    "turc", "hindi", "vietnamien", "roumain", "grec", "hébreu", "hebreu", "ukrainien", "catalan", "berbère",
    "kabyle", "wolof", "tamoul", "bengali", "persan", "farsi", "english", "french", "spanish", "german",
)
_LANGUAGE_NAME_RE = re.compile(r"(?<![\w-])(" + "|".join(_LANGUAGE_NAMES) + r")(?![\w-])", re.I)
_LANGUAGE_LEVEL_RE = re.compile(
    r"\b(?:natif|native|maternelle?|bilingue|courant|fluent|avanc[ée]|interm[ée]diaire|technique|professionnel(?:le)?"
    r"|notions?|scolaire|lu|parl[ée]|[ée]crit|[abc][12]|toeic|toefl|ielts|langue de travail)\b",
    re.I,
)
_LANGUAGE_LINE_RE = re.compile(r"^\s*(?:langues?|languages?)\b", re.I)
_CERT_RE = re.compile(
    r"certifi|\bcertified\b|\bpsm\s*(?:i{1,3}|[123])\b|\bpspo\b|\bpsd\b|\bcsm\b|\bcspo\b|\bpmp\b|\bcapm\b|prince\s*2"
    r"|\b(?:az|dp|ai|ms|pl|sc|md)-\d{3}\b|\bcka\b|\bckad\b|\bcks\b|\brhcsa\b|\brhce\b|\bocp\b|\bmcsa\b|\bmcse\b|\bmcts\b"
    r"|itil\s*(?:v?\d|foundation|4)|togaf\s*(?:\d|certified|foundation)|\bistqb\b|green\s*belt|black\s*belt|yellow\s*belt"
    r"|safe\s*\d|\bsafe\s+(?:agilist|sa|spc|popm)\b|\bfia\s*\d{3}\b|\btoeic\b",
    re.I,
)
_SOFT_SKILL_PHRASES = (
    "adaptabilite", "adaptable", "autonomie", "autonome", "rigueur", "rigoureux", "rigoureuse", "curiosite", "curieux",
    "esprit d equipe", "travail en equipe", "esprit d analyse", "esprit de synthese", "esprit critique", "sens de l ecoute",
    "ecoute", "ecoute active", "force de proposition", "capacite d apprentissage", "apprentissage rapide", "proactivite",
    "proactif", "proactive", "creativite", "creatif", "empathie", "gestion du stress", "resistance au stress", "pedagogie",
    "pedagogue", "polyvalence", "polyvalent", "dynamisme", "dynamique", "reactivite", "reactif", "ponctualite",
    "perseverance", "bienveillance", "leadership", "communication", "aisance relationnelle", "sens relationnel",
    "relationnel", "organisation", "organise", "sens de l organisation", "sens des responsabilites", "esprit d initiative",
    "prise d initiative", "patience", "diplomatie", "assertivite", "resolution de problemes", "flexibilite",
    "motivation", "motive", "serieux", "implication", "fiabilite", "sens du service", "esprit de service",
    "intelligence emotionnelle", "gestion des priorites", "gestion du temps", "capacite d adaptation", "travail collaboratif",
    "esprit collaboratif", "collaboration", "sens du detail", "souci du detail", "methodique", "ouverture d esprit",
    "soft skills", "savoir etre",
)
_SOFT_CATEGORY_RE = re.compile(r"soft\s*skills?|savoir[-\s]?[êe]tre|qualit[ée]s|comp[ée]tences\s+(?:comportementales|personnelles|humaines|relationnelles|transverses)|atouts|personal skills", re.I)
_ACTION_VERB_RE = re.compile(
    r"^(?:mettre|participer|r[ée]diger|piloter|accompagner|concevoir|assurer|r[ée]aliser|animer|analyser|g[ée]rer|d[ée]velopper"
    r"|impl[ée]menter|d[ée]ployer|migrer|maintenir|former|encadrer|coordonner|superviser|d[ée]finir|identifier|optimiser|automatiser"
    r"|garantir|contribuer|[ée]laborer|suivre|pr[ée]parer|organiser|pr[ée]senter|produire|tester|cr[ée]er|am[ée]liorer|mener"
    r"|r[ée]dig[ée]|d[ée]velopp[ée]|particip[ée]|con[çc]u|r[ée]alis[ée]|pilot[ée]|mis en place|j['’]ai|responsable de)\b",
    re.I,
)
_HEADING_ITEMS = {
    "competences", "competences techniques", "competences fonctionnelles", "soft skills", "langues", "langue", "certifications",
    "formation", "formations", "experiences", "experience", "projets", "realisations", "outils", "education", "etudes",
    "technologies", "skills", "hard skills", "autres", "divers", "environnement technique", "stack technique",
    "secteurs", "secteurs d activite", "domaines", "domaines fonctionnels", "domaines de competences", "methodologies",
    "outils et methodes", "langages", "frameworks", "bases de donnees", "competences cles", "expertises", "savoir faire",
}
_PROJECT_CATEGORY_RE = re.compile(r"projets?|r[ée]alisations?", re.I)
_CONTINUED_CATEGORY_RE = re.compile(r"\s*(?:\((?:suite|cont\.?)\)|[-–—]\s*suite(?:\s*\d+)?)\s*$", re.I)
_GENERIC_CATEGORY_KEYS = {"autres", "divers", "competences", "skills", "technologies", "compétences", "autres competences"}
_CITIES = (
    "paris", "lyon", "marseille", "lille", "toulouse", "nantes", "bordeaux", "nice", "strasbourg", "rennes", "montpellier",
    "grenoble", "tunis", "casablanca", "rabat", "alger", "meudon", "la defense", "bruxelles", "geneve", "luxembourg",
    "londres", "london", "montreal", "nanterre", "courbevoie", "puteaux", "issy les moulineaux", "boulogne billancourt",
    "levallois", "saint denis", "massy", "velizy", "guyancourt", "rueil malmaison", "neuilly", "clichy", "montrouge",
    "orleans", "tours", "dijon", "reims", "rouen", "caen", "brest", "nancy", "metz", "aix en provence", "toulon", "niort",
    "le mans", "angers", "poitiers", "limoges", "pau", "sophia antipolis", "ile de france", "remote", "teletravail",
)


def _word_count(text: str) -> int:
    without_parens = re.sub(r"\([^)]*\)", " ", text)
    return len([w for w in re.split(r"\s+", without_parens) if re.search(r"\w", w)])


def is_soft_skill(item: str) -> bool:
    folded = _fold(item)
    if not folded:
        return False
    if folded in _SOFT_SKILL_PHRASES:
        return True
    # « Autonomie et proactivité », « Rigueur, curiosité »
    parts = [p.strip() for p in re.split(r"\bet\b|,|/|&", folded) if p.strip()]
    return bool(parts) and all(p in _SOFT_SKILL_PHRASES for p in parts)


def is_language_item(item: str) -> bool:
    text = _clean_text(item)
    if _LANGUAGE_LINE_RE.match(text):
        return True
    names = _LANGUAGE_NAME_RE.findall(text)
    if not names:
        return False
    rest = _LANGUAGE_NAME_RE.sub(" ", text)
    rest = _LANGUAGE_LEVEL_RE.sub(" ", rest)
    rest = re.sub(r"\b(?:langue|langues|niveau|score|et|de|du|la|le|chez|quotidienne|travail|sur|\d+)\b", " ", rest, flags=re.I)
    rest = re.sub(r"[\W_]+", " ", rest).strip()
    # Le reste ne doit pas porter de technologie (« Java Anglais » reste une compétence).
    return len(rest.split()) <= 2


def parse_languages(item: str) -> list[dict[str, str]]:
    text = re.sub(r"^\s*(?:langues?|languages?)\s*[:：-]?\s*", "", _clean_text(item), flags=re.I)
    matches = list(_LANGUAGE_NAME_RE.finditer(text))
    out: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        level = text[match.end():end].strip(" :：-–—,;()").strip()
        level = re.sub(r"[()]", "", level).strip(" ,;")
        name = match.group(1)
        out.append({"name": name[:1].upper() + name[1:].lower(), "level": level[:60]})
    return out


def is_certification_item(item: str) -> bool:
    text = _clean_text(item)
    return bool(_CERT_RE.search(text)) and _word_count(text) <= 8 and len(text) <= 90


def is_education_item(item: str) -> bool:
    text = _clean_text(item)
    if re.search(r"\bscrum master\b|\bmaster data\b|\bmasterclass\b|\bmaster\s+(?:branch|node|slave)\b", text, re.I):
        text = re.sub(r"\bscrum master\b|\bmaster data\b|\bmasterclass\b", " ", text, flags=re.I)
    if _EDUCATION_UPPER_RE.search(text):
        return True
    return bool(_EDUCATION_RE.search(text)) and not re.fullmatch(r"(?i)formation(?:s)?\s+(?:des|aux|utilisateurs?).*", text)


def has_mission_date(item: str) -> bool:
    if _DATE_RE.search(item):
        return True
    match = _YEAR_RANGE_RE.search(item)
    if not match:
        return False
    return match.start() <= 2 or _word_count(item) >= 5 or bool(re.match(r"\s*:", item[match.end():]))


def _is_city_fragment(item: str) -> bool:
    folded = _fold(item)
    return any(folded == city or folded.startswith(city + " ") for city in _CITIES)


def is_phrase(item: str) -> bool:
    text = _clean_text(item)
    words = _word_count(text)
    if len(text) > MAX_SKILL_CHARS or words > MAX_SKILL_WORDS:
        return True
    if words >= 3 and _ACTION_VERB_RE.match(text):
        return True
    if words >= 4 and text.endswith("."):
        return True
    # « risques. Data & Cloud », « hallucinations). Collaboration »
    if re.search(r"[a-zà-ÿ)]\.\s+[A-ZÀ-Ý]", text) and words >= 3:
        return True
    return False


# --------------------------------------------------------------------------- outils

def _category_label(category: str) -> str:
    label = re.sub(r"\s+", " ", str(category or "")).strip(" :•-–—")
    previous = None
    while previous != label:
        previous = label
        label = _CONTINUED_CATEGORY_RE.sub("", label).strip(" :•-–—")
    return label


def _split_top_level(text: str, separators: str = r",|;|\s·\s|·|•|\s\|\s") -> list[str]:
    """Découpe sur les séparateurs hors parenthèses : « Jira (Xray, Zephyr) » reste entier."""
    parts: list[str] = []
    depth = 0
    start = 0
    for match in re.finditer(r"[()]|" + separators, text):
        token = match.group(0)
        if token == "(":
            depth += 1
        elif token == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            parts.append(text[start:match.start()])
            start = match.end()
    parts.append(text[start:])
    return [p for p in (part.strip() for part in parts) if p]


def _rejoin_open_parentheses(items: list[str], lookahead: int = 5) -> list[str]:
    """Recolle les fragments d'une découpe sur les virgules :
    « React (TypeScript », « Redux) » -> « React (TypeScript, Redux) ».
    Seulement si la parenthèse se referme dans les `lookahead` items suivants ;
    sinon chaque fragment est réparé à part (repair_parentheses)."""
    out: list[str] = []
    index = 0
    while index < len(items):
        item = items[index]
        if item.count("(") > item.count(")"):
            joined = item
            closed_at = None
            for offset in range(1, lookahead + 1):
                if index + offset >= len(items):
                    break
                nxt = items[index + offset]
                if nxt.count("(") > nxt.count(")"):
                    break
                joined = f"{joined}, {nxt}"
                if joined.count("(") <= joined.count(")"):
                    closed_at = index + offset
                    break
            if closed_at is not None:
                out.append(joined)
                index = closed_at + 1
                continue
        out.append(item)
        index += 1
    return out


def repair_parentheses(item: str) -> str:
    text = item.strip()
    # Fermantes en trop au début / à la fin : « Redux) », « (MCP ».
    while text.endswith(")") and text.count(")") > text.count("("):
        text = text[:-1].rstrip(" ,;")
    while text.startswith("(") and text.count("(") > text.count(")"):
        text = text[1:].lstrip(" ,;")
    while text.count(")") > text.count("("):
        index = text.find(")")
        text = (text[:index] + text[index + 1:]).strip()
    if text.count("(") > text.count(")"):
        head, _, tail = text.rpartition("(")
        tail = tail.strip(" ,;")
        if tail and _word_count(tail) <= 4:
            text = f"{head.rstrip()} ({tail})"
        else:
            text = (head.rstrip() + " " + tail).strip()
    if text.startswith("(") and text.endswith(")") and text.count("(") == 1:
        text = text[1:-1].strip()
    text = re.sub(r"\(\s*\)", "", text).strip()
    return text


def _experience_haystacks(data: dict) -> tuple[str, str, list[str]]:
    """(texte des expériences, texte des en-têtes d'expérience, sociétés)."""
    body: list[str] = []
    headers: list[str] = []
    companies: list[str] = []
    for exp in data.get("experiences") or []:
        if not isinstance(exp, dict):
            continue
        headers.extend(str(exp.get(key) or "") for key in ("date", "role", "company_highlight"))
        company = _clean_text(str(exp.get("company_highlight") or ""))
        if len(company) >= 3:
            companies.append(company)
        for section in exp.get("sections") or []:
            if not isinstance(section, dict):
                continue
            body.append(str(section.get("heading") or ""))
            content = section.get("content")
            body.extend(str(c) for c in content) if isinstance(content, list) else body.append(str(content or ""))
    for project in data.get("projects") or []:
        if isinstance(project, dict):
            body.append(str(project.get("name") or ""))
            body.extend(str(d) for d in project.get("details") or [])
    return _fold(" ".join(body + headers)), _fold(" ".join(headers)), companies


def _mentions_company(item: str, companies: list[str]) -> bool:
    folded = _fold(item)
    if _word_count(item) < 3:
        return False
    for company in companies:
        key = _fold(company)
        if len(key) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", folded):
            return True
    return False


def source_skill_categories(source_text: str) -> dict[str, str]:
    """Clé d'item -> catégorie, lue dans la section Compétences du CV d'origine
    (lignes « Libellé : a, b, c » éventuellement coupées en plusieurs lignes)."""
    lines = _extract_skills_lines(source_text or "")
    mapping: dict[str, str] = {}
    current_label: str | None = None
    current_values: list[str] = []

    def flush() -> None:
        if current_label:
            for value in _split_top_level(" ".join(current_values), r",|;|/|\s·\s|·|•"):
                value = repair_parentheses(_clean_text(value))
                key = skill_key(value)
                if key and key not in mapping and _word_count(value) <= 5:
                    mapping[key] = current_label

    for raw in lines[:80]:
        # Trailing comma kept: "Excel," + "SQL(SSMS)" are two values.
        line = re.sub(r"\s+", " ", str(raw or "")).strip(" |•·▪➢✓-–—\t")
        match = re.match(r"^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ&/' -]{2,39}?)\s*[:：]\s*(.*)$", line)
        if match and _word_count(match.group(1)) <= 4 and not has_mission_date(line):
            flush()
            current_label = _category_label(match.group(1))
            current_values = [match.group(2)]
            continue
        if current_label and ((current_values and current_values[-1].rstrip().endswith(",")) or "/" in line or "," in line):
            current_values.append(line)
            continue
        flush()
        current_label, current_values = None, []
    flush()
    return mapping



# Libellés de catégorie en capitales recollés dans un item par l'extraction :
# « IBM Mainframe SYSTÈMES OS/400 », « VSAM METHODOLOGIES Merise ».
_UPPER_LABELS = (
    "AUTRES OUTILS", "OUTILS DEBUG", "OUTILS VERSIONING", "OUTILS DE TEST", "BASES DE DONNÉES", "BASES DE DONNEES",
    "SOFT SKILLS", "HARD SKILLS", "MATÉRIEL", "MATERIEL", "SYSTÈMES", "SYSTEMES", "LANGAGES", "OUTILS", "MÉTHODOLOGIES",
    "METHODOLOGIES", "MÉTHODES", "METHODES", "BUREAUTIQUE", "LOGICIELS", "FRAMEWORKS", "ENVIRONNEMENTS", "RÉSEAUX",
    "RESEAUX", "COMPÉTENCES TECHNIQUES", "COMPETENCES TECHNIQUES", "COMPÉTENCES", "COMPETENCES", "LANGUES",
)
_UPPER_LABEL_RE = re.compile(r"(?<![\w/-])(?:" + "|".join(re.escape(label) for label in _UPPER_LABELS) + r")(?![\w/-])")


def _split_uppercase_labels(text: str) -> list[str]:
    if not _UPPER_LABEL_RE.search(text):
        return [text]
    parts = [p.strip(" ,;:.") for p in _UPPER_LABEL_RE.split(text)]
    return [p for p in parts if p] or []


def _logical_source_lines(lines: list[str]) -> list[str]:
    """Lignes de la section Compétences du CV d'origine, avec les listes
    « Libellé : a, b, » coupées en fin de ligne recollées."""
    out: list[str] = []
    for raw in lines:
        line = _clean_text(raw)
        if not line:
            continue
        if out and (
            out[-1].endswith((",", "/", ":"))
            or (re.match(r"^[^:：]{3,40}[:：]", out[-1]) and ("/" in line or "," in line) and ":" not in line)
            or re.match(r"^[a-zà-ÿ(]", line)
        ):
            out[-1] = f"{out[-1]} {line}" if not out[-1].endswith("/") else out[-1] + line
            continue
        out.append(line)
    return out


def _split_slash_list(text: str) -> list[str]:
    parts = [p.strip() for p in text.split("/")]
    if len(parts) > 1 and all(len(p) >= 3 and re.match(r"^[A-ZÀ-Ý0-9]", p) for p in parts):
        return parts
    return [text]


def _decompose_with_source_lines(item: str, source_lines: list[str]) -> list[str]:
    """Un item qui recolle plusieurs lignes de la section Compétences du CV
    d'origine (« Secteurs Banque Gestion de projet agile (Scrum) … ») est
    redécoupé selon ces lignes."""
    if _word_count(item) <= MAX_SKILL_WORDS or not source_lines or re.search(r"[,;·•]", item):
        return []
    folded_item = f" {_fold(item)} "
    found: list[tuple[int, str]] = []
    covered = 0
    for line in sorted(set(source_lines), key=len, reverse=True):
        folded_line = _fold(line)
        if len(folded_line) < 3:
            continue
        position = folded_item.find(f" {folded_line} ")
        if position < 0:
            continue
        found.append((position, line))
        covered += len(folded_line) + 1
        folded_item = folded_item[:position] + " " + "_" * len(folded_line) + " " + folded_item[position + len(folded_line) + 2:]
    if not found or covered < 0.7 * len(_fold(item)):
        return []
    return [line for _, line in sorted(found)]


_LABELLED_SKILL_LIST_RE = re.compile(
    r"(?:comp[ée]tences\s+cl[ée]s|environnement(?:\s+technique)?|stack(?:\s+technique)?|outils|technologies|langages)\s*[:：]\s*([^.;]+)",
    re.I,
)


def _labelled_skill_values(text: str) -> list[str]:
    """Listes « Compétences clés : Python, Jira, Agile Scrum » d'un texte de
    mission : ce sont des compétences du CV, à garder quand le texte part."""
    values: list[str] = []
    for match in _LABELLED_SKILL_LIST_RE.finditer(text or ""):
        for value in _split_top_level(match.group(1), r","):
            value = repair_parentheses(_clean_text(value))
            if value and _word_count(value) <= 4 and not has_mission_date(value) and not _is_city_fragment(value):
                values.append(value)
    return values


# Familles pour vider « Autres » (en plus de skills_intelligence) : mots entiers.
_FAMILY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Tests & Qualité", ("test", "tests", "pytest", "junit", "jest", "selenium", "cypress", "playwright", "appium", "postman",
                         "squash", "xray", "jmeter", "cucumber", "gherkin", "bdd", "tdd", "recette", "non regression", "qualite",
                         "sonarqube", "testflight", "browserstack", "alm", "robot framework", "katalon", "soapui")),
    ("Data & IA", ("pandas", "numpy", "tensorflow", "pytorch", "keras", "scikit", "spark", "hadoop", "llm", "langchain", "rag",
                   "cnn", "lstm", "rnn", "machine learning", "deep learning", "ia", "ai", "nlp", "computer vision", "ocr",
                   "power bi", "tableau", "qlik", "databricks", "snowflake", "etl", "talend", "airflow", "dbt", "looker",
                   "embeddings", "faiss", "chroma", "pinecone", "hugging face", "openai", "mlops", "data")),
    ("Langages", ("python", "java", "kotlin", "swift", "scala", "rust", "go", "golang", "ruby", "php", "perl", "c", "c++", "c#",
                  "typescript", "javascript", "bash", "shell", "powershell", "vba", "cobol", "r", "dart", "matlab", "groovy")),
    ("Outils & Environnements", ("jira", "confluence", "git", "github", "gitlab", "bitbucket", "figma", "excel", "notion", "miro",
                                 "trello", "asana", "slack", "teams", "sharepoint", "office", "visual studio", "vs code",
                                 "intellij", "eclipse", "postman", "uipath", "power automate", "servicenow", "glpi", "klaxoon")),
)


def _family_for(item: str) -> str | None:
    folded = f" {_fold(item)} "
    for family, keywords in _FAMILY_KEYWORDS:
        if any(f" {_fold(k)} " in folded for k in keywords):
            return family
    return _category_for_skill_value(item)


_FRENCH_NOUN_SUFFIX_RE = re.compile(r"(?:age|tion|sion|ment|ance|ence|it[ée]|ure|aire|i[èe]re|eur|euse|ique|ies?|ises?|ats?)$", re.I)


def _looks_like_common_word(item: str) -> bool:
    """« paiement », « Paramétrage », « échéance » : mots courants, pas des
    noms d'outils (« Citrix », « Freshservice », « SSH », « F5 »)."""
    text = item.strip()
    words = text.split()
    if re.match(r"^[a-zà-ÿ]", text) and len(words) > 1:
        return True
    if len(words) != 1 or re.search(r"[A-ZÀ-Ý0-9]", text[1:]) or "-" in text and not re.search(r"[à-ÿ]", text):
        return False
    return bool(_FRENCH_NOUN_SUFFIX_RE.search(text)) and bool(re.search(r"[à-ÿ]", text) or len(text) >= 8)


def _mission_list_fragments(experiences: list[dict]) -> set[str]:
    """Morceaux de listes des phrases de mission (« (Réception facture, TVA,
    échéance) », « Paramétrage, recette et suivi… ») : une découpe sur les
    virgules les a fait passer pour des compétences. Les sections
    d'environnement technique sont exclues (leurs listes sont des outils)."""
    fragments: set[str] = set()
    for exp in experiences:
        for section in exp.get("sections") or []:
            if not isinstance(section, dict):
                continue
            if re.search(r"(?i)environnement|stack|outils|technolog|comp[ée]tences", str(section.get("heading") or "")):
                continue
            content = section.get("content")
            for bullet in content if isinstance(content, list) else [content]:
                text = str(bullet or "")
                if _word_count(text) < 6:
                    continue
                for part in re.split(r"[,;()]", text):
                    folded = _fold(part)
                    if folded and len(folded.split()) <= 3:
                        fragments.add(folded)
    return fragments


def _in_text(item: str, haystack_folded: str) -> bool:
    folded = _fold(item)
    return bool(folded) and f" {folded} " in f" {haystack_folded} "


def _experience_for_item(item: str, experiences: list[dict]) -> dict | None:
    if _word_count(item) < 3:
        return None
    folded = _fold(item)
    for exp in experiences:
        key = _fold(str(exp.get("company_highlight") or ""))
        if len(key) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", folded):
            return exp
    return None


def _after_company(item: str, experience: dict) -> str:
    company = str(experience.get("company_highlight") or "")
    words = [re.escape(w) for w in re.split(r"\s+", company.strip()) if w]
    if not words:
        return ""
    match = re.search(r"(?<!\w)" + r"\W+".join(words) + r"(?!\w)", item, re.I)
    if not match:
        return ""
    return item[match.end():].strip(" :：-–—,;|")


def _add_context(experience: dict, text: str) -> None:
    sections = experience.setdefault("sections", [])
    for section in sections:
        if isinstance(section, dict) and _fold(str(section.get("heading") or "")) == "contexte":
            content = section.get("content")
            if isinstance(content, list):
                content.append(text)
            else:
                section["content"] = [str(content or ""), text] if content else [text]
            return
    sections.insert(0, {"heading": "Contexte", "content": [text]})


# --------------------------------------------------------------------------- passe principale

def clean_skills_section(
    data: dict,
    source_text: str = "",
    *,
    keep_soft_skills: bool = False,
    max_items_per_category: int = MAX_ITEMS_PER_CATEGORY,
) -> dict:
    """Retourne une copie de `data` dont `skills` ne contient que des
    compétences ; le détail des actions est dans `data[CLEANUP_REPORT_KEY]`."""
    if not isinstance(data, dict) or not isinstance(data.get("skills"), list):
        return data
    out = deepcopy(data)
    report: list[dict[str, Any]] = list(out.get(CLEANUP_REPORT_KEY) or [])

    def note(action: str, item: str, category: str, target: str = "") -> None:
        entry = {"action": action, "item": item[:600], "category": category}
        if target:
            entry["target"] = target
        report.append(entry)

    exp_text, header_text, companies = _experience_haystacks(out)
    formations = [f for f in out.get("formations") or [] if isinstance(f, dict)]
    formation_text = _fold(" ".join(" ".join(str(f.get(k) or "") for k in ("date", "degree", "school")) for f in formations))
    certifications = [str(c) for c in out.get("certifications") or [] if str(c).strip()]
    cert_keys = {skill_key(c) for c in certifications}
    cert_text = _fold(" ".join(certifications))
    languages = [l for l in out.get("languages") or [] if isinstance(l, dict) or isinstance(l, str)]
    language_names = {_fold(l.get("name") if isinstance(l, dict) else l) for l in languages}
    projects = [p for p in out.get("projects") or [] if isinstance(p, dict)]
    source_categories = source_skill_categories(source_text)
    source_lines = _logical_source_lines(_extract_skills_lines(source_text or ""))
    source_labels = {skill_key(label): label for label in source_categories.values()}
    skills_block = _fold(" ".join(source_lines))
    experiences = [e for e in out.get("experiences") or [] if isinstance(e, dict)]
    mission_fragments = _mission_list_fragments(experiences)

    # 1. Catégories : libellés sans « (suite) », fusion des homonymes.
    ordered: list[tuple[str, list[str]]] = []
    index_by_key: dict[str, int] = {}
    for skill in out.get("skills") or []:
        if not isinstance(skill, dict):
            continue
        raw_category = str(skill.get("category") or "")
        category = _category_label(raw_category) or "Autres"
        if category != raw_category.strip():
            note("categorie_renommee", raw_category, raw_category, category)
        items = [str(i) for i in skill.get("items") or [] if str(i).strip()]
        key = skill_key(category)
        if key in index_by_key:
            ordered[index_by_key[key]][1].extend(items)
            note("categorie_fusionnee", category, raw_category, ordered[index_by_key[key]][0])
        else:
            index_by_key[key] = len(ordered)
            ordered.append((category, items))

    # 2. Items : découpe des listes collées, recollage des parenthèses.
    expanded: list[tuple[str, list[str]]] = []
    deferred: list[tuple[str, list[str]]] = []
    for category, items in ordered:
        pieces: list[str] = []
        for item in items:
            text = _clean_text(item)
            for part in _split_top_level(text, r";|\s·\s|·|•|\s\|\s|\|"):
                sentences = [p for p in re.split(r"(?<=[\wà-ÿ)])\.\s+(?=[A-ZÀ-Ýa-z])", part) if p.strip()]
                if len(sentences) > 1 and all(_word_count(p) <= MAX_SKILL_WORDS for p in sentences):
                    for fragment in sentences[:-1]:
                        if re.match(r"^[a-zà-ÿ]", fragment) and not _in_text(fragment, skills_block):
                            note("fragment_de_phrase_supprime", fragment, category)
                            sentences.remove(fragment)
                    note("phrase_redecoupee", part, category, " | ".join(sentences)[:200])
                    part = sentences[0] if len(sentences) == 1 else part
                    if len(sentences) > 1:
                        pieces.extend(sentences)
                        continue
                labelled = _split_uppercase_labels(part)
                if labelled != [part]:
                    note("libelle_majuscule_retire", part, category, " | ".join(labelled)[:200])
                pieces.extend(labelled)
        # Une virgule hors parenthèse sépare deux compétences, sauf dans une phrase.
        split_pieces: list[str] = []
        decomposed: list[str] = []
        for piece in pieces:
            lines = _decompose_with_source_lines(piece, source_lines)
            if lines:
                note("liste_source_redecoupee", piece, category, " | ".join(lines)[:200])
                decomposed.extend(lines)
            else:
                decomposed.append(piece)
        later: list[str] = []
        for piece in decomposed:
            target = later if piece not in pieces else split_pieces
            if is_phrase(piece) or has_mission_date(piece):
                target.append(piece)
            else:
                target.extend(_split_top_level(piece, r","))
        expanded.append((category, _rejoin_open_parentheses(split_pieces)))
        for piece in _rejoin_open_parentheses(later):
            # Catégorie du CV d'origine, sinon famille technique, sinon « Autres ».
            target = source_categories.get(skill_key(piece)) or _category_for_skill_value(piece) or "Autres"
            deferred.append((target, [piece]))
    # Les lignes retrouvées dans un item recollé passent après les items
    # rangés par le modèle : un doublon garde la catégorie du modèle.
    expanded.extend(deferred)

    all_items_text = [item for _, items in expanded for item in items]
    relabelled: list[tuple[str, list[str]]] = []
    salvaged: list[tuple[str, str]] = []
    kept: list[tuple[str, list[str]]] = []
    seen: dict[str, str] = {}
    queue = list(expanded)
    while queue or relabelled:
        if not queue:
            queue.extend(relabelled)
            relabelled.clear()
        category, items = queue.pop(0)
        category_is_soft = bool(_SOFT_CATEGORY_RE.search(category))
        category_is_language = bool(re.fullmatch(r"(?i)langues?|languages?|comp[ée]tences linguistiques", category))
        category_is_cert = bool(re.fullmatch(r"(?i)certifications?|certificats?|titres?\s*/?\s*certifications?", category))
        category_is_education = bool(re.fullmatch(r"(?i)formations?|dipl[oô]mes?|[ée]ducation|[ée]tudes|cursus", category))
        category_is_project = bool(_PROJECT_CATEGORY_RE.fullmatch(category.strip()) or re.match(r"(?i)(?:exemples? de )?(?:projets?|r[ée]alisations?)\b", category))
        kept_items: list[str] = []
        for raw_item in items:
            item = _clean_text(raw_item)
            if not item:
                continue
            original = repair_parentheses(item)
            # « Programmation : Python » -> le libellé collé n'est pas une compétence.
            label_match = re.match(r"^([A-Za-zÀ-ÿ&/' -]{3,40}?)\s*[:：]\s*(\S.*)$", item)
            if label_match and _word_count(label_match.group(1)) <= 4 and not is_language_item(item) and not has_mission_date(item):
                label = _category_label(label_match.group(1))
                rest = label_match.group(2).strip()
                if skill_key(label) in source_labels and not is_phrase(rest):
                    # « Gestion de projet : Azure Devops/Jira » : catégorie du CV d'origine.
                    values = [v for part in _split_top_level(rest, r",|;") for v in _split_slash_list(part)]
                    relabelled.append((source_labels[skill_key(label)], values))
                    note("reclasse_categorie_source", item, category, source_labels[skill_key(label)])
                    continue
                note("libelle_colle_retire", label_match.group(1), category)
                item = rest
            repaired = repair_parentheses(item)
            if repaired != item:
                note("parenthese_reparee", item, category, repaired)
                item = repaired
            item = _clean_text(item)
            if not item:
                continue
            folded = _fold(item)
            if folded in _HEADING_ITEMS:
                note("titre_retire", item, category)
                continue

            # Langue parlée.
            if category_is_language or is_language_item(item):
                parsed = parse_languages(item)
                if parsed:
                    for lang in parsed:
                        if _fold(lang["name"]) in language_names:
                            note("langue_deja_presente", item, category, "languages")
                        else:
                            languages.append(lang if lang["level"] else {"name": lang["name"]})
                            language_names.add(_fold(lang["name"]))
                            note("deplace_vers_langues", item, category, "languages")
                    continue
                if category_is_language:
                    note("supprime_langue_illisible", item, category)
                    continue

            # Texte d'une mission (société d'une expérience citée) : rangé dans
            # l'expérience s'il n'y est pas déjà, sinon supprimé.
            experience = _experience_for_item(original, experiences)
            if experience is not None:
                remainder = _after_company(original, experience)
                remainder = repair_parentheses(_clean_text(remainder)) if remainder else ""
                if not remainder or _word_count(remainder) < 2 or _coverage(remainder, exp_text) >= 0.8:
                    note("texte_de_mission_supprime", original, category, "experiences")
                    salvaged.extend((category, value) for value in _labelled_skill_values(original))
                else:
                    _add_context(experience, remainder)
                    exp_text += " " + _fold(remainder)
                    note("deplace_vers_experience", original, category, str(experience.get("company_highlight") or ""))
                continue

            # Formation / diplôme / école.
            if category_is_education or is_education_item(item):
                if _coverage(item, formation_text + " " + cert_text) >= 0.6 or _coverage(item, formation_text + " " + exp_text) >= 0.8:
                    note("formation_deja_presente", item, category, "formations")
                else:
                    date_match = re.search(r"(?:19|20)\d{2}(?:\s*[-–—/]\s*(?:19|20)\d{2})?", item)
                    degree = _clean_text(re.sub(r"(?:19|20)\d{2}(?:\s*[-–—/]\s*(?:19|20)\d{2})?\s*:?", " ", item))
                    formations.append({"date": date_match.group(0) if date_match else "", "degree": degree, "school": ""})
                    formation_text += " " + _fold(item)
                    note("deplace_vers_formations", item, category, "formations")
                continue

            # Certification.
            if (category_is_cert and _word_count(item) <= 10) or is_certification_item(item):
                if skill_key(item) in cert_keys or _coverage(item, cert_text) >= 0.8:
                    note("certification_deja_presente", item, category, "certifications")
                else:
                    certifications.append(item)
                    cert_keys.add(skill_key(item))
                    cert_text += " " + _fold(item)
                    note("deplace_vers_certifications", item, category, "certifications")
                continue

            # Soft skill.
            if not keep_soft_skills and (category_is_soft or is_soft_skill(item)):
                note("soft_skill_supprime", item, category)
                continue

            # Texte de mission ou phrase.
            from_source_skills = _in_text(item, skills_block)
            in_experiences = _word_count(item) >= 3 and _in_text(item, exp_text)
            if (
                not from_source_skills
                and _word_count(item) <= 3
                and _fold(item) in mission_fragments
                and _family_for(item) is None
                and _looks_like_common_word(item)
                and skill_key(item) not in source_categories
            ):
                note("fragment_de_mission_supprime", item, category, "experiences")
                continue
            lowercase_fragment = bool(re.match(r"^[a-zà-ÿ]", item)) and not from_source_skills and (
                _in_text(item, exp_text) or (_word_count(item) >= 3 and _coverage(item, exp_text) >= 0.8)
            )
            mission_like = (
                lowercase_fragment
                or has_mission_date(original)
                or is_phrase(item)
                or (_is_city_fragment(item) and _coverage(item, header_text) >= 1.0)
                or (in_experiences and not from_source_skills)
                or (category_is_project and _word_count(item) >= 5)
            )
            if mission_like:
                if in_experiences or lowercase_fragment or (not from_source_skills and _coverage(item, exp_text) >= 0.8):
                    note("texte_de_mission_supprime", original, category, "experiences")
                    salvaged.extend((category, value) for value in _labelled_skill_values(original))
                    continue
                others = " ".join(other for other in all_items_text if other is not raw_item)
                if is_phrase(item) and _coverage(item, exp_text + " " + formation_text + " " + _fold(others)) >= 0.85:
                    note("phrase_redondante_supprimee", original, category)
                    salvaged.extend((category, value) for value in _labelled_skill_values(original))
                    continue
                if (category_is_project and _word_count(item) >= 5) or has_mission_date(original):
                    projects.append({"name": "", "date": "", "details": [original]})
                    exp_text += " " + _fold(original)
                    note("deplace_vers_projets", original, category, "projects")
                    continue
                if is_phrase(item):
                    note("phrase_conservee", item, category)

            key = skill_key(item)
            if not key:
                continue
            if key in seen:
                note("doublon_supprime", item, category, seen[key])
                continue
            seen[key] = category
            kept_items.append(item)
        if kept_items:
            kept.append((category, kept_items))
        elif items:
            note("categorie_videe", category, category)

    # Compétences des listes « Compétences clés : … » d'un texte de mission retiré.
    for origin, value in salvaged:
        key = skill_key(value)
        if not key or key in seen:
            continue
        seen[key] = origin
        target = source_categories.get(key) or _category_for_skill_value(value) or "Autres"
        index = next((i for i, (c, _) in enumerate(kept) if skill_key(c) == skill_key(target)), None)
        if index is None:
            kept.append((target, [value]))
        else:
            kept[index][1].append(value)
        note("competence_recuperee", value, origin, target)

    # 3. « Autres » / catégories génériques : vers les catégories du CV d'origine
    #    puis vers une catégorie existante de même famille.
    existing = {skill_key(c): i for i, (c, _) in enumerate(kept)}
    regrouped: list[tuple[str, list[str]]] = [(c, list(items)) for c, items in kept]

    def add_to(category: str, item: str) -> None:
        # « Langages » rejoint « Langages & Frameworks », « Data & IA » rejoint « Data & BI »…
        head = _fold(category).split(" ")[0] if _fold(category) else ""
        if skill_key(category) not in existing and head:
            similar = next((c for c, _ in regrouped if _fold(c).split(" ")[0] == head), None)
            if similar:
                category = similar
        key = skill_key(category)
        if key not in existing:
            existing[key] = len(regrouped)
            regrouped.append((category, []))
        regrouped[existing[key]][1].append(item)

    for index, (category, items) in enumerate(list(regrouped)):
        is_project_category = bool(re.match(r"(?i)(?:exemples? de )?(?:projets?|r[ée]alisations?)\b", category))
        if skill_key(category) not in {skill_key(c) for c in _GENERIC_CATEGORY_KEYS} and not is_project_category:
            continue
        remaining: list[str] = []
        for item in items:
            target = source_categories.get(skill_key(item))
            if target and skill_key(target) != skill_key(category):
                add_to(target, item)
                note("reclasse_categorie_source", item, category, target)
                continue
            family = _family_for(item)
            if family and skill_key(family) in existing and skill_key(family) != skill_key(category):
                add_to(family, item)
                note("reclasse_categorie_existante", item, category, family)
                continue
            if is_project_category:
                # Pas de catégorie « Projets » dans les compétences.
                add_to(family or "Autres", item)
                note("reclasse_hors_projets", item, category, family or "Autres")
                continue
            remaining.append(item)
        # Une famille qui regroupe au moins 3 items de « Autres » devient une catégorie.
        by_family: dict[str, list[str]] = {}
        for item in remaining:
            family = _family_for(item)
            if family and skill_key(family) != skill_key(category):
                by_family.setdefault(family, []).append(item)
        for family, family_items in by_family.items():
            if len(family_items) >= 3:
                for item in family_items:
                    remaining.remove(item)
                    add_to(family, item)
                    note("reclasse_nouvelle_categorie", item, category, family)
        regrouped[index] = (category, remaining)

    # 4. Catégories trop longues : découpe par famille (noms distincts, jamais « suite »).
    final: list[tuple[str, list[str]]] = []
    for category, items in regrouped:
        if not items:
            continue
        if len(items) <= max_items_per_category:
            final.append((category, items))
            continue
        by_family: dict[str, list[str]] = {}
        rest: list[str] = []
        for item in items:
            family = _family_for(item)
            if family and skill_key(family) != skill_key(category):
                by_family.setdefault(family, []).append(item)
            else:
                rest.append(item)
        final.append((category, rest))
        for family, family_items in by_family.items():
            final.append((family, family_items))
            for item in family_items:
                note("reclasse_categorie_trop_longue", item, category, family)
    merged: list[tuple[str, list[str]]] = []
    merged_index: dict[str, int] = {}
    for category, items in final:
        if not items:
            continue
        key = skill_key(category)
        if key in merged_index:
            merged[merged_index[key]][1].extend(i for i in items if i not in merged[merged_index[key]][1])
        else:
            merged_index[key] = len(merged)
            merged.append((category, list(items)))
    # « Autres » en dernier, une seule fois.
    merged.sort(key=lambda entry: skill_key(entry[0]) in {"autres", "divers"})
    for category, items in merged:
        if len(items) > max_items_per_category:
            note("categorie_longue_conservee", f"{category} ({len(items)} items)", category)

    # Items composés d'autres items (« React JavaScript », « Docker Kubernetes ») ou
    # égaux à un nom de catégorie (« Cloud / DevOps »).
    all_keys = {skill_key(i) for _, items in merged for i in items}
    category_keys = {skill_key(c) for c, _ in merged} | {skill_key(c) for c in source_labels.values()}
    for index, (category, items) in enumerate(merged):
        kept_final: list[str] = []
        for item in items:
            key = skill_key(item)
            if key in category_keys:
                note("titre_retire", item, category)
                continue
            words = [w for w in re.split(r"\s+/\s+|\s+", item) if w]
            if "(" not in item and 2 <= len(words) <= 4 and all(skill_key(w) in all_keys and skill_key(w) != key for w in words):
                note("doublon_supprime", item, category, "items séparés")
                continue
            kept_final.append(item)
        merged[index] = (category, kept_final)
    merged = [(c, items) for c, items in merged if items]
    # Trop de catégories : les plus petites rejoignent une catégorie de même famille, sinon « Autres ».
    while len(merged) > MAX_CATEGORIES:
        sizes = sorted(range(len(merged)), key=lambda i: len(merged[i][1]))
        smallest = next((i for i in sizes if skill_key(merged[i][0]) not in {"autres"} and len(merged[i][1]) <= 3), None)
        if smallest is None:
            break
        category, items = merged.pop(smallest)
        for item in items:
            family = _category_for_skill_value(item)
            target = next((i for i, (c, _) in enumerate(merged) if family and skill_key(c) == skill_key(family)), None)
            if target is None:
                target = next((i for i, (c, _) in enumerate(merged) if skill_key(c) == "autres"), None)
            if target is None:
                merged.append(("Autres", []))
                target = len(merged) - 1
            merged[target][1].append(item)
            note("categorie_regroupee", item, category, merged[target][0])
    merged.sort(key=lambda entry: skill_key(entry[0]) in {"autres", "divers"})

    # Certifications : « PSPO I, Lean Six Sigma » quand les deux existent déjà.
    deduped_certs: list[str] = []
    for cert in certifications:
        parts = [p.strip() for p in re.split(r"[,;]", cert) if p.strip()]
        others = {skill_key(c) for c in certifications if c is not cert}
        if len(parts) > 1 and all(skill_key(p) in others for p in parts):
            note("certification_doublon_supprimee", cert, "certifications")
            continue
        if skill_key(cert) in {skill_key(c) for c in deduped_certs}:
            note("certification_doublon_supprimee", cert, "certifications")
            continue
        deduped_certs.append(cert)
    certifications = deduped_certs
    out["skills"] = [{"category": c, "items": items} for c, items in merged]
    if formations or out.get("formations") is not None:
        out["formations"] = formations
    if certifications or out.get("certifications") is not None:
        out["certifications"] = certifications
    if languages or out.get("languages") is not None:
        out["languages"] = languages
    if projects:
        out["projects"] = projects
    out[CLEANUP_REPORT_KEY] = report
    meaningful = [e for e in report if e["action"] not in {"categorie_renommee", "parenthese_reparee"}]
    if meaningful:
        log.info("skills_cleanup actions=%d %s", len(meaningful), summarize_cleanup(report))
    return out


def summarize_cleanup(report: list[dict[str, Any]] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in report or []:
        action = str(entry.get("action") or "")
        counts[action] = counts.get(action, 0) + 1
    return counts


def cleanup_qa_warning(report: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Avertissement QA lisible : ce qui a été déplacé ou supprimé des compétences."""
    moved = [e for e in report or [] if str(e.get("action", "")).startswith("deplace_vers_")]
    removed = [
        e for e in report or []
        if e.get("action") in {
            "texte_de_mission_supprime", "soft_skill_supprime", "doublon_supprime", "formation_deja_presente",
            "langue_deja_presente", "certification_deja_presente", "titre_retire", "supprime_langue_illisible",
            "phrase_redondante_supprimee", "certification_doublon_supprimee", "fragment_de_mission_supprime",
            "fragment_de_phrase_supprime",
        }
    ]
    if not moved and not removed:
        return None
    lines = [f"{e['item']} -> {e.get('target')}" for e in moved] + [f"{e['item']} ({e['action']})" for e in removed]
    return {
        "code": "skills_cleanup",
        "message": f"Compétences nettoyées : {len(moved)} élément(s) déplacé(s), {len(removed)} supprimé(s).",
        "moved": [{"item": e["item"], "target": e.get("target"), "from": e.get("category")} for e in moved],
        "removed": [{"item": e["item"], "reason": e["action"], "from": e.get("category")} for e in removed],
        "details": lines[:200],
    }
