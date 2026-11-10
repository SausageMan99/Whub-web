"""Lot 3 (2026-11) : plus aucune suppression silencieuse dans la structuration.

Données anonymisées.
"""
import logging

import pytest

from src.content_log import CONTENT_WARNINGS_KEY
from src import structuring as st


@pytest.mark.parametrize("line", [
    "Plateforme installée chez 40 clients grands comptes",
    "Migration de 15000 postes de travail vers Windows 11",
    "Refonte de la gestion des allées et venues des visiteurs",
    "Application de suivi des avenues de croissance du portefeuille",
])
def test_coverage_exclusion_is_not_a_substring_match(line):
    assert st._is_allowed_source_coverage_exclusion(line) is False


@pytest.mark.parametrize("line", [
    "12 rue de la Paix",
    "3 bis, avenue Victor Hugo",
    "75008 Paris",
    "Rue des Lilas, appartement 4",
])
def test_coverage_exclusion_still_drops_real_addresses(line):
    assert st._is_allowed_source_coverage_exclusion(line) is True


def test_coverage_facts_keep_lines_with_installee_or_five_digits():
    source = "PROJETS\n• Solution installée chez 15000 utilisateurs en agence\nFORMATIONS\n2015 Master"

    facts = [f["fact"] for f in st.extract_source_business_coverage_facts(source)]

    assert any("installée chez 15000 utilisateurs" in fact for fact in facts)


def test_certification_category_keeps_every_item_and_logs_doubts():
    data = {
        "skills": [{"category": "Certifications", "items": [
            "PSM I", "Formation Lean Management interne (2 jours)", "PSM I",
        ]}],
        "certifications": [],
    }

    out = st._postprocess_skills_into_languages_and_certifications(data)

    assert out["certifications"] == ["PSM I", "Formation Lean Management interne (2 jours)"]
    codes = [w["code"] for w in out[CONTENT_WARNINGS_KEY]]
    assert codes.count("certification_kept_unverified") == 1
    assert codes.count("certification_duplicate_removed") == 1
    assert out["skills"] == []


def test_prompt_truncation_is_logged(caplog):
    long_source = ("Expérience de mission chez un client bancaire. " * 1200).strip()
    assert len(st.compact_extracted_text(long_source)) > st.MAX_PROMPT_CV_CHARS

    with caplog.at_level(logging.WARNING, logger="whub-cv-worker.structuring"):
        text, cut = st._prompt_source_text(st.compact_extracted_text(long_source))

    assert len(text) == st.MAX_PROMPT_CV_CHARS
    assert cut > 0
    assert any("truncated" in record.message for record in caplog.records)


def test_short_prompt_source_is_not_cut():
    text, cut = st._prompt_source_text("CV court")
    assert (text, cut) == ("CV court", 0)


def test_prompt_states_language_dates_and_empty_values_rules():
    prompt = st._hermes_prompt("CV source", "", [], "Ines")

    assert "ne traduis rien" in prompt
    assert "Non spécifié" in prompt and "chaîne vide" in prompt
    assert "Aujourd'hui" in prompt
    assert "antichronologique" in prompt


def test_content_warnings_are_not_checked_as_cv_text():
    """Le journal peut citer un texte retiré : la fidélité ne le lit pas."""
    data = {
        "name": "Ines", "title": "Analyste", "formations": [], "skills": [],
        "experiences": [{"date": "2020 – 2021", "role": "Analyste", "company_highlight": "Acme",
                         "sections": [{"heading": "Missions clés", "content": ["Analyse des flux de paiement"]}]}],
        CONTENT_WARNINGS_KEY: [{"code": "x", "message": "Texte inventé 99 Inexistant Corp"}],
    }
    source = "Ines\nAnalyste\n2020 – 2021 Analyste Acme\nAnalyse des flux de paiement\n" + "Texte de remplissage. " * 30

    st.validate_source_fidelity(source, data, forbidden_identity_terms=[])
