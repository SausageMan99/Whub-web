"""Journal des suppressions et corrections de contenu (lot 3, 2026-11).

Toute étape déterministe qui retire, coupe ou réécrit du contenu du CV
(structuration, passe de finition) l'écrit ici, dans la clé
`data["_content_warnings"]` du JSON structuré. La QA (`qa.run_qa`) la reprend
dans `report["content_warnings"]` : rien n'est retiré en silence.

Chaque entrée : {"code", "message", ...détails}. Les codes connus sont dans
CONTENT_WARNING_CODES (libellés courts pour l'affichage).
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("whub-cv-worker.content")

CONTENT_WARNINGS_KEY = "_content_warnings"

CONTENT_WARNING_CODES: dict[str, str] = {
    # Structuration
    "prompt_source_truncated": "CV source coupé avant l'envoi au modèle",
    "certification_kept_unverified": "Élément de la catégorie Certifications conservé tel quel",
    "certification_duplicate_removed": "Certification en double retirée",
    # Passe de finition (src/content_finishing.py)
    "placeholder_removed": "Valeur vide ou « Non spécifié » retirée",
    "page_furniture_removed": "En-tête / pied de page du CV source retiré du contenu",
    "date_normalized": "Date mise au format commun",
    "experiences_reordered": "Expériences remises dans l'ordre antichronologique",
    "experience_order_unverified": "Ordre des expériences non vérifiable (date illisible)",
    "duplicate_experience_merged": "Expérience répétée fusionnée",
    "company_sentence_split": "Phrase de contexte sortie du champ entreprise",
    "text_repaired": "Texte réparé (ligature, lettre détachée, ponctuation)",
    "bullet_rejoined": "Puce coupée en deux recollée",
    "word_completed_from_source": "Mot coupé complété depuis le CV source",
    "gap_filled_from_source": "Mot manquant rétabli depuis le CV source",
    "skill_item_removed": "Élément retiré des compétences (prénom, titre ou en-tête)",
    # Détections QA (avertissements, rien n'est modifié)
    "truncated_text": "Texte qui semble tronqué",
    "future_end_date": "Date de fin dans le futur",
    "company_field_sentence": "Champ entreprise rempli par une phrase",
    "description_too_short": "Description trop courte",
    "content_language_not_french": "Contenu du CV en anglais (non traduit)",
    "broken_ligature": "Mot coupé par une ligature perdue",
    "content_missing_from_pdf": "Contenu du JSON absent du PDF",
}


def add_content_warning(data: dict, code: str, message: str, **details: Any) -> None:
    """Ajoute une entrée au journal du JSON `data` (et au log du worker)."""
    if not isinstance(data, dict):
        return
    entry: dict[str, Any] = {"code": code, "message": message}
    entry.update({k: v for k, v in details.items() if v is not None})
    data.setdefault(CONTENT_WARNINGS_KEY, [])
    if entry not in data[CONTENT_WARNINGS_KEY]:
        data[CONTENT_WARNINGS_KEY].append(entry)
    log.info("content_warning code=%s", code)


def content_warnings(data: dict | None) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    return [w for w in data.get(CONTENT_WARNINGS_KEY) or [] if isinstance(w, dict)]
