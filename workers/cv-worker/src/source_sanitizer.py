from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SanitizationReport:
    raw_chars: int
    sanitized_chars: int
    removed_email_count: int = 0
    removed_phone_count: int = 0
    removed_url_count: int = 0
    removed_linkedin_count: int = 0
    removed_github_profile_count: int = 0
    removed_address_line_count: int = 0
    removed_contact_label_line_count: int = 0
    removed_hellowork_line_count: int = 0
    removed_empty_or_boilerplate_line_count: int = 0
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceSanitizationResult:
    text: str
    report: SanitizationReport


class SourceSanitizationError(Exception):
    pass


EMAIL_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
PHONE_RE = re.compile(
    r"(?<!\d)(?:0[67][ .-]?(?:\d{2}[ .-]?){3}\d{2}|\+33[ .-]?[67][ .-]?(?:\d{2}[ .-]?){3}\d{2})(?!\d)",
    re.I,
)
LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:fr\.)?linkedin\.com/in/\S+|(?:https?://)?lnkd\.in/\S+",
    re.I,
)
GITHUB_PROFILE_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9-]+\b/?", re.I)
URL_RE = re.compile(
    r"https?://\S+|www\.\S+|(?<!\w)(?:[a-z0-9-]+\.)+(?:dev|io|app|fr|com|net|org|co|ai|me|xyz|eu|uk|de|es|it|be|ca|ch)(?:/[^\s)]*)?(?!\w)",
    re.I,
)

CONTACT_LABEL_ONLY_RE = re.compile(
    r"^(?:coordonn[ée]es?|contact|t[ée]l(?:[ée]phone)?|mobile|email|mail|e-mail|linkedin|github|portfolio|site\s+web)\s*:?$",
    re.I,
)
CONTACT_LABEL_PREFIX_RE = re.compile(
    r"^(?:coordonn[ée]es?|contact|t[ée]l(?:[ée]phone)?|mobile|email|mail|e-mail|linkedin|github|portfolio|site\s+web)\s*:?\s*$",
    re.I,
)

HELLOWORK_LINE_RE = re.compile(
    r"\b(?:cv\s+t[ée]l[ée]charg[ée]|t[ée]l[ée]charg[ée]\s+depuis|profil\s+consult[ée]|voir\s+le\s+profil|mettre\s+[àa]\s+jour\s+mon\s+cv|candidature|disponibilit[ée]|dispo\s*:|tjm|salaire\s+souhait[ée]|pr[ée]tentions?|pr[ée]tention\s+salariale|permis|mobilit[ée]|type\s+de\s+contrat|contrat\s+souhait[ée]|m[ée]tier\s+recherch[ée]|poste\s+recherch[ée]|d[ée]but|pr[ée]avis)\b",
    re.I,
)
HELLOWORK_WORD_RE = re.compile(r"\bhellowork\b", re.I)

POSTAL_CITY_RE = re.compile(r"\b\d{5}\s+[A-ZÀ-ÖØ-Þa-zà-öø-ÿ][A-ZÀ-ÖØ-Þa-zà-öø-ÿ' -]{2,}\b")
STREET_RE = re.compile(
    r"^\s*\d{1,4}\s+(?:rue|avenue|av\.?|boulevard|bd\.?|chemin|impasse|all[ée]e|route|place|quai|cours)\b",
    re.I,
)
ADDRESS_PREFIX_RE = re.compile(r"^\s*(?:adresse|domicile|domicili[ée]|habite)\b\s*:?.*", re.I)

_EMPTY_PUNCT_RE = re.compile(r"^[\s,;:|/\\•\-–—()\[\].]+$")


def sanitize_source_text(
    raw_text: str,
    candidate_first_name: str | None = None,
    *,
    min_chars: int = 400,
) -> SourceSanitizationResult:
    """Remove obvious contact/ATS noise from source CV text before model structuring.

    The returned report contains only counters and generic warning codes: never raw
    removed values or source snippets.
    """
    raw = "" if raw_text is None else str(raw_text)
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")

    removed_email_count = 0
    removed_phone_count = 0
    removed_url_count = 0
    removed_linkedin_count = 0
    removed_github_profile_count = 0
    removed_address_line_count = 0
    removed_contact_label_line_count = 0
    removed_hellowork_line_count = 0
    removed_empty_or_boilerplate_line_count = 0
    warnings: list[str] = []

    kept_lines: list[str] = []
    previous_line_was_street_address = False

    for index, original_line in enumerate(normalized.split("\n")):
        line = original_line.strip()
        if not line:
            kept_lines.append("")
            previous_line_was_street_address = False
            continue

        in_header = index < 25
        if _is_hellowork_or_ats_line(line):
            removed_hellowork_line_count += 1
            previous_line_was_street_address = False
            continue

        if CONTACT_LABEL_ONLY_RE.fullmatch(line):
            removed_contact_label_line_count += 1
            previous_line_was_street_address = False
            continue

        if _is_header_address_line(line, in_header, previous_line_was_street_address):
            removed_address_line_count += 1
            previous_line_was_street_address = bool(STREET_RE.search(line) or ADDRESS_PREFIX_RE.search(line))
            continue

        previous_line_was_street_address = False
        cleaned, counts = _sanitize_inline_contacts(line)
        removed_email_count += counts["email"]
        removed_phone_count += counts["phone"]
        removed_linkedin_count += counts["linkedin"]
        removed_github_profile_count += counts["github"]
        removed_url_count += counts["url"]

        cleaned = _cleanup_contact_residue(cleaned)
        if not cleaned or _EMPTY_PUNCT_RE.fullmatch(cleaned) or CONTACT_LABEL_PREFIX_RE.fullmatch(cleaned):
            removed_empty_or_boilerplate_line_count += 1
            continue
        kept_lines.append(cleaned)

    sanitized = _collapse_blank_lines("\n".join(kept_lines))
    if raw and len(sanitized) < max(1, int(len(raw) * 0.55)):
        warnings.append("sanitized_text_shrunk_unusually")
    if removed_hellowork_line_count:
        warnings.append("hellowork_boilerplate_removed")

    report = SanitizationReport(
        raw_chars=len(raw),
        sanitized_chars=len(sanitized),
        removed_email_count=removed_email_count,
        removed_phone_count=removed_phone_count,
        removed_url_count=removed_url_count,
        removed_linkedin_count=removed_linkedin_count,
        removed_github_profile_count=removed_github_profile_count,
        removed_address_line_count=removed_address_line_count,
        removed_contact_label_line_count=removed_contact_label_line_count,
        removed_hellowork_line_count=removed_hellowork_line_count,
        removed_empty_or_boilerplate_line_count=removed_empty_or_boilerplate_line_count,
        warnings=tuple(dict.fromkeys(warnings)),
    )

    if len(sanitized.strip()) < min_chars:
        raise SourceSanitizationError("Texte source trop court après sanitization")

    return SourceSanitizationResult(text=sanitized, report=report)


def _is_hellowork_or_ats_line(line: str) -> bool:
    # A bare Hellowork mention inside a real experience sentence is useful
    # business content; remove it only when paired with known export/ATS noise.
    if HELLOWORK_LINE_RE.search(line):
        return True
    folded = line.casefold()
    if HELLOWORK_WORD_RE.search(line) and any(token in folded for token in ("cv", "profil", "candidat", "télécharg", "telecharg")):
        return True
    return False


def _is_header_address_line(line: str, in_header: bool, previous_line_was_street_address: bool) -> bool:
    address_candidate = _strip_leading_contact_icon(line)
    if ADDRESS_PREFIX_RE.search(address_candidate):
        return True
    if not in_header:
        return False
    if STREET_RE.search(address_candidate):
        return True
    if previous_line_was_street_address and POSTAL_CITY_RE.search(address_candidate):
        return True
    if POSTAL_CITY_RE.search(address_candidate) and not re.search(r"\b(?:mission|chez|client|exp[ée]rience|projet|remote|full-stack)\b", address_candidate, re.I):
        return True
    return False


def _strip_leading_contact_icon(line: str) -> str:
    """Drop decorative PDF icon glyphs before address detection.

    Hellowork-style exports can prefix email/phone/address lines with private-use
    icon glyphs (for example ``3 rue de Genève``). Address detection should see
    the business text after the icon, without mutating non-contact content.
    """
    return re.sub(r"^[^\w\dÀ-ÖØ-öø-ÿ]+", "", line or "").strip()


def _sanitize_inline_contacts(line: str) -> tuple[str, dict[str, int]]:
    counts = {"email": 0, "phone": 0, "linkedin": 0, "github": 0, "url": 0}
    cleaned = line
    cleaned, counts["email"] = EMAIL_RE.subn("", cleaned)
    cleaned, counts["phone"] = PHONE_RE.subn("", cleaned)
    cleaned, counts["linkedin"] = LINKEDIN_RE.subn("", cleaned)
    cleaned, counts["github"] = GITHUB_PROFILE_RE.subn("", cleaned)
    cleaned, counts["url"] = URL_RE.subn("", cleaned)
    return cleaned, counts


def _cleanup_contact_residue(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"\(\s*(?:lien|site|url|portfolio|linkedin|github|contact)\s*:?\s*\)", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(?:lien|url)\s*:\s*(?=$|[),.;])", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s+([,;:])", r"\1", cleaned)
    cleaned = re.sub(r"\s+\.(?!\s*(?:NET|Net|net)\b)", ".", cleaned)
    cleaned = re.sub(r"(?:\s*[-–—|•]\s*){2,}", " - ", cleaned)
    cleaned = re.sub(r"^[\s,;:|•\-–—]+|[\s,;:|•\-–—]+$", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
    return cleaned


def _collapse_blank_lines(text: str) -> str:
    lines = [line.rstrip() for line in text.split("\n")]
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        if not line.strip():
            if collapsed and not previous_blank:
                collapsed.append("")
            previous_blank = True
            continue
        collapsed.append(line.strip())
        previous_blank = False
    return "\n".join(collapsed).strip()
