from __future__ import annotations

import pytest

from src.revisions import classify_revision_intent


def test_classifies_move_last_mission_to_page_3_as_layout_only():
    body = "Déplacer la dernière mission en page 3"
    intent = classify_revision_intent(body)
    assert intent.kind == "layout_only"


def test_classifies_move_to_page_X_as_layout_only():
    body = "Mettre cette expérience en page 2"
    assert classify_revision_intent(body).kind == "layout_only"


def test_classifies_derniere_page_remonter_as_layout_only():
    body = "Mettre les dernières expériences en dernière page et remonter"
    assert classify_revision_intent(body).kind == "layout_only"


def test_classifies_aer_page_2_as_layout_only():
    body = "Aérer la page 2 et resserrer la page 1"
    assert classify_revision_intent(body).kind == "layout_only"


def test_classifies_saut_de_page_correction_as_layout_only():
    body = "Corriger le saut de page entre la section expérience et la formation"
    assert classify_revision_intent(body).kind == "layout_only"


def test_classifies_missing_experience_as_content():
    body = "Mission manquant"
    assert classify_revision_intent(body).kind == "content"


def test_classifies_corrige_le_texte_as_content():
    body = "Corriger le texte de la mission chez Thales"
    assert classify_revision_intent(body).kind == "content"


def test_classifies_empty_body_as_unknown():
    assert classify_revision_intent("").kind == "unknown"
    assert classify_revision_intent("   ").kind == "unknown"
    assert classify_revision_intent(None).kind == "unknown"


def test_classifies_bare_phrase_as_unknown_when_neither_keyword_matches():
    body = "C'est super, merci beaucoup pour ton aide !"
    assert classify_revision_intent(body).kind == "unknown"
