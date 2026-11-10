"""Hiérarchie des défauts d'un CV rendu (lot 4, 2026-11).

Les lots 1 à 5 ont ajouté des mesures sur le PDF rendu (pagination,
couverture JSON -> PDF, textes tronqués, finitions) en simples
avertissements : un CV défectueux partait quand même. Ce module classe
chaque défaut à un seul endroit, en trois niveaux :

BLOQUANT (``blocking``) — le CV ne doit pas partir tel quel :
  - ``content_missing_from_pdf`` : du contenu du JSON n'apparaît pas dans le
    PDF (perte de contenu) ;
  - ``text_overflow`` : du texte déborde de la zone lisible de la page ;
  - ``truncated_text`` : une puce ou un texte tronqué par le moteur (le
    même texte coupé tel quel dans le CV source n'est qu'un avertissement,
    ``truncated_in_source``) ;
  - ``page_nearly_empty`` : une page autre que la dernière remplie à moins
    de 40 % alors que le CV continue ;
  - ``heading_orphaned_at_page_bottom`` : titre seul en bas de page ;
  - ``placeholder_printed`` : « Non spécifié », « N/A », « () » imprimé ;
  - ``page_furniture_printed`` : reste d'en-tête / pied de page du CV source.
  Réaction (src/layout/__init__.py run_layout, src/main.py) : réessai
  ciblé, d'abord des variantes de mise en page déterministes (sans LLM),
  puis, pour un défaut d'origine « contenu » et si un modèle est configuré,
  une seule restructuration avec ``_corrective_retry_prompt``. Si le défaut
  persiste, le CV n'est pas livré en silence : perte de contenu -> statut
  ``qa_failed`` (« Bloqué » sur le site, version visible mais non
  téléchargeable) ; autre défaut -> ``draft_ready`` (« À relire ») avec le
  défaut en tête des points à vérifier.

AVERTISSEMENT (``warning``) — le relecteur doit vérifier : page
intermédiaire remplie entre 40 et 60 %, dernière page sous 35 %, suite
courte, page 1 sans expérience, dates futures, contenu en anglais,
description courte, champ entreprise = phrase, typographie cassée,
compétences nettoyées, ordre des expériences invérifiable, CV source coupé
avant structuration, texte tronqué dans le CV source même.

JOURNAL (``info``) — corrections automatiques déjà faites et tracées
(dates mises au format, puces recollées, doublons fusionnés…) : gardées dans
``qa_report["content_warnings"]``, pas affichées comme points à vérifier.

Toute nouvelle mesure doit être ajoutée à ``DEFECT_RULES`` : un code inconnu
est traité en avertissement, jamais ignoré.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

BLOCKING = "blocking"
WARNING = "warning"
INFO = "info"

# Origine d'un défaut : « layout » se répare par une variante de mise en page,
# « content » vient du JSON structuré (réessai de structuration possible).
LAYOUT = "layout"
CONTENT = "content"

# Page autre que la dernière : sous 40 % elle est « quasi vide » (bloquant),
# entre 40 et 60 % elle est à vérifier (qa.PAGINATION_INTERMEDIATE_MIN_FILL).
PAGE_NEARLY_EMPTY_FILL = 0.40


@dataclass(frozen=True)
class DefectRule:
    severity: str
    origin: str
    content_loss: bool = False


DEFECT_RULES: dict[str, DefectRule] = {
    # --- bloquants
    "content_missing_from_pdf": DefectRule(BLOCKING, LAYOUT, content_loss=True),
    "text_overflow": DefectRule(BLOCKING, LAYOUT),
    "truncated_text": DefectRule(BLOCKING, CONTENT),
    "page_nearly_empty": DefectRule(BLOCKING, LAYOUT),
    "heading_orphaned_at_page_bottom": DefectRule(BLOCKING, LAYOUT),
    "placeholder_printed": DefectRule(BLOCKING, CONTENT),
    "page_furniture_printed": DefectRule(BLOCKING, CONTENT),
    # --- avertissements
    "page_underfilled": DefectRule(WARNING, LAYOUT),
    "last_page_nearly_empty": DefectRule(WARNING, LAYOUT),
    "short_continuation": DefectRule(WARNING, LAYOUT),
    "first_page_without_experience": DefectRule(WARNING, LAYOUT),
    "truncated_in_source": DefectRule(WARNING, CONTENT),
    "future_end_date": DefectRule(WARNING, CONTENT),
    "content_language_not_french": DefectRule(WARNING, CONTENT),
    "description_too_short": DefectRule(WARNING, CONTENT),
    "company_field_sentence": DefectRule(WARNING, CONTENT),
    "broken_ligature": DefectRule(WARNING, CONTENT),
    "experience_order_unverified": DefectRule(WARNING, CONTENT),
    "prompt_source_truncated": DefectRule(WARNING, CONTENT),
    "certification_kept_unverified": DefectRule(WARNING, CONTENT),
    "skills_cleaned": DefectRule(WARNING, CONTENT),
    # --- journal (corrections faites et tracées)
    "placeholder_removed": DefectRule(INFO, CONTENT),
    "page_furniture_removed": DefectRule(INFO, CONTENT),
    "date_normalized": DefectRule(INFO, CONTENT),
    "experiences_reordered": DefectRule(INFO, CONTENT),
    "duplicate_experience_merged": DefectRule(INFO, CONTENT),
    "company_sentence_split": DefectRule(INFO, CONTENT),
    "text_repaired": DefectRule(INFO, CONTENT),
    "bullet_rejoined": DefectRule(INFO, CONTENT),
    "word_completed_from_source": DefectRule(INFO, CONTENT),
    "gap_filled_from_source": DefectRule(INFO, CONTENT),
    "skill_item_removed": DefectRule(INFO, CONTENT),
    "skill_removed": DefectRule(INFO, CONTENT),
    "certification_duplicate_removed": DefectRule(INFO, CONTENT),
}

_DEFAULT_RULE = DefectRule(WARNING, CONTENT)


def rule_for(code: str) -> DefectRule:
    return DEFECT_RULES.get(code, _DEFAULT_RULE)


def _defect(code: str, message: str, *, page: int | None = None, **extra: Any) -> dict[str, Any]:
    rule = rule_for(code)
    item: dict[str, Any] = {
        "code": code,
        "severity": rule.severity,
        "origin": rule.origin,
        "content_loss": rule.content_loss,
        "message": message,
    }
    if isinstance(page, int):
        item["page"] = page
    item.update({key: value for key, value in extra.items() if value is not None})
    return item


# ------------------------------------------------------------ truncated text

def _words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", str(text or "")).replace("’", "'")
    return re.findall(r"[0-9A-Za-zÀ-ÿ+#']+|[()]", text)


def truncation_reproduces_source(item: dict[str, Any], source_text: str | None) -> bool:
    """True when a text flagged as truncated is copied as is from the source.

    The CV source itself may end a line on an open parenthesis or a cut
    sentence: copying it faithfully is not an engine defect (66515bc8). The
    item is faithful when its whole word sequence is in the source and, for
    an ending on a function word or a comma, the source does not go on with
    the same sentence (next word in lower case)."""
    if not source_text:
        return False
    words = _words(item.get("text") or "")
    source_words = _words(source_text)
    if len(words) < 3 or not source_words:
        return False
    lowered = [w.lower() for w in words]
    source_lowered = [w.lower() for w in source_words]
    size = len(lowered)
    first = lowered[0]
    for start, word in enumerate(source_lowered):
        if word != first or source_lowered[start:start + size] != lowered:
            continue
        reason = str(item.get("reason") or "")
        if reason in ("fin_sur_mot_outil", "fin_sur_virgule"):
            following = source_words[start + size] if start + size < len(source_words) else ""
            if following and following[:1].islower():
                return False
        return True
    return False


# ------------------------------------------------------------ collection

_PATH_TOKEN_RE = re.compile(r"([A-Za-z_]+)|\[(\d+)\]")


def _value_at(data: Any, path: str) -> Any:
    """Value of `data` at a content_finishing path like
    "experiences[3].sections[0].content[1]" (None when absent)."""
    value = data
    for name, index in _PATH_TOKEN_RE.findall(path or ""):
        if name:
            value = value.get(name) if isinstance(value, dict) else None
        else:
            position = int(index)
            value = value[position] if isinstance(value, list) and position < len(value) else None
        if value is None:
            return None
    return value


def collect_defects(
    report: dict[str, Any],
    source_text: str | None = None,
    structured_data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Every defect of a QA report (qa.run_qa), with its severity.

    Reads report["pagination"], ["text_overflow_hits"], ["content_coverage"],
    ["content_warnings"] and ["skills_cleanup"]; the former layout_issues and
    content_integrity_issues keep their own path (qa.classify_qa_report)."""
    defects: list[dict[str, Any]] = []
    pagination = report.get("pagination") if isinstance(report.get("pagination"), dict) else {}
    for warning in pagination.get("warnings") or []:
        if not isinstance(warning, dict):
            continue
        code = str(warning.get("code") or "")
        page = warning.get("page") if isinstance(warning.get("page"), int) else None
        message = str(warning.get("message") or code)
        if code == "page_underfilled":
            fill = float(warning.get("fill") or 0.0)
            if fill < PAGE_NEARLY_EMPTY_FILL:
                defects.append(_defect("page_nearly_empty", message, page=page, fill=round(fill, 3)))
            else:
                defects.append(_defect("page_underfilled", message, page=page, fill=round(fill, 3)))
            continue
        extra = {key: warning.get(key) for key in ("fill", "lines_under") if isinstance(warning.get(key), (int, float))}
        defects.append(_defect(code, message, page=page, **extra))

    overflow = [hit for hit in report.get("text_overflow_hits") or [] if isinstance(hit, dict)]
    for page in sorted({hit.get("page") for hit in overflow if isinstance(hit.get("page"), int)}):
        hits = [hit for hit in overflow if hit.get("page") == page]
        defects.append(_defect(
            "text_overflow", f"Texte hors de la zone lisible page {page} ({len(hits)} bloc(s))",
            page=page, count=len(hits),
        ))

    for warning in report.get("content_warnings") or []:
        if not isinstance(warning, dict) or not warning.get("code"):
            continue
        code = str(warning["code"])
        message = str(warning.get("message") or code)
        if code == "truncated_text":
            items = [item for item in warning.get("items") or [] if isinstance(item, dict)]
            if isinstance(structured_data, dict):
                # The warning keeps 200 characters: compare the whole text.
                items = [
                    {**item, "text": full} if isinstance(full := _value_at(structured_data, str(item.get("path") or "")), str) else item
                    for item in items
                ]
            engine = [item for item in items if not truncation_reproduces_source(item, source_text)]
            faithful = [item for item in items if item not in engine]
            if engine:
                defects.append(_defect(
                    "truncated_text", f"{len(engine)} texte(s) tronqué(s) par la mise au format",
                    count=len(engine), items=[{**i, "text": str(i.get("text") or "")[:200]} for i in engine[:10]],
                ))
            if faithful:
                defects.append(_defect(
                    "truncated_in_source", f"{len(faithful)} texte(s) coupé(s) tel quel dans le CV source",
                    count=len(faithful), items=[{**i, "text": str(i.get("text") or "")[:200]} for i in faithful[:10]],
                ))
            if not items:
                defects.append(_defect("truncated_text", message))
            continue
        if code == "content_missing_from_pdf":
            items = [item for item in warning.get("items") or [] if isinstance(item, dict)]
            defects.append(_defect(code, message, count=len(items), items=items[:10]))
            continue
        extra = {"count": len(warning["items"])} if isinstance(warning.get("items"), list) else {}
        defects.append(_defect(code, message, **extra))

    if report.get("skills_cleanup"):
        defects.append(_defect("skills_cleaned", "Compétences rangées ou retirées par le nettoyage"))
    return defects


def blocking_defects(defects: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [d for d in defects or [] if isinstance(d, dict) and d.get("severity") == BLOCKING]


def warning_defects(defects: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [d for d in defects or [] if isinstance(d, dict) and d.get("severity") == WARNING]


def report_blocking_defects(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    return blocking_defects((report or {}).get("defects"))


def has_content_loss(defects: list[dict[str, Any]] | None) -> bool:
    return any(d.get("content_loss") for d in blocking_defects(defects))


def blocking_origins(defects: list[dict[str, Any]] | None) -> set[str]:
    return {str(d.get("origin")) for d in blocking_defects(defects)}


def blocking_summary(defects: list[dict[str, Any]] | None) -> str:
    """One French line naming the blocking defects (status reason, logs)."""
    items = blocking_defects(defects)
    if not items:
        return ""
    parts = []
    for item in items:
        message = str(item.get("message") or item.get("code"))
        if isinstance(item.get("page"), int) and "page" not in message.lower():
            message += f" (page {item['page']})"
        parts.append(message)
    return "; ".join(parts)[:480]


def corrective_diagnostic(defects: list[dict[str, Any]] | None) -> str:
    """Diagnostic given to _corrective_retry_prompt for content defects:
    codes, messages and the faulty texts, never contact data (the JSON was
    sanitized before rendering)."""
    lines = []
    for item in blocking_defects(defects):
        if item.get("origin") != CONTENT:
            continue
        lines.append(f"- {item['code']}: {item.get('message')}")
        for detail in item.get("items") or []:
            text = detail.get("text") if isinstance(detail, dict) else str(detail)
            if text:
                lines.append(f"    « {str(text)[:200]} »")
    if not lines:
        return ""
    return (
        "qa_blocking_content_defects: le PDF rendu présente des défauts de contenu bloquants. "
        "Recopie ces passages en entier depuis le CV source (aucune phrase coupée, aucune valeur "
        "« Non spécifié » ou vide, aucun en-tête ou pied de page du document source) :\n"
        + "\n".join(lines)
    )


__all__ = [
    "BLOCKING", "WARNING", "INFO", "LAYOUT", "CONTENT", "PAGE_NEARLY_EMPTY_FILL",
    "DefectRule", "DEFECT_RULES", "rule_for", "collect_defects", "blocking_defects",
    "warning_defects", "report_blocking_defects", "has_content_loss", "blocking_origins",
    "blocking_summary", "corrective_diagnostic", "truncation_reproduces_source",
]
