"""Lots 3 et 5 (2026-11) : passe de finition du contenu. Données anonymisées."""
from datetime import date

import pytest

from src.content_finishing import (
    content_qa_warnings,
    experiences_out_of_order,
    finalize_cv_content,
    find_placeholders,
    find_truncated_texts,
    format_date_text,
    looks_truncated,
)
from src.content_log import CONTENT_WARNINGS_KEY


def _exp(date_text, role="Analyste", company="Acme", content=None, heading="Missions clés"):
    return {
        "date": date_text, "role": role, "company_highlight": company,
        "sections": [{"heading": heading, "content": list(content or ["Analyse des flux de paiement"])}],
    }


def _cv(**extra):
    data = {
        "name": "Ines", "title": "Analyste fonctionnelle", "description": "Analyste fonctionnelle, dix ans de projets bancaires et assurance.",
        "formations": [], "certifications": [], "languages": [], "skills": [], "experiences": [_exp("2020 – 2021")],
    }
    data.update(extra)
    return data


def _codes(data):
    return [w["code"] for w in data.get(CONTENT_WARNINGS_KEY) or []]


@pytest.mark.parametrize("raw, expected", [
    ("09/2023 – 05/2024", "Sept. 2023 – Mai 2024"),
    ("Juin 2026-Déc 2026", "Juin 2026 – Déc. 2026"),
    ("01/2026 – Present", "Janv. 2026 – Aujourd'hui"),
    ("depuis 03/2025", "Mars 2025 – Aujourd'hui"),
    ("05/2026 -> aujourd'hui", "Mai 2026 – Aujourd'hui"),
    ("2019 – 2019", "2019"),
    ("2002/2003", "2002 – 2003"),
    ("2024-26", "2024 – 2026"),
    ("Du 21/06/2023 Au 04/05/2026", "Juin 2023 – Mai 2026"),
    ("AVRIL 2025 A AVRIL 2026", "Avr. 2025 – Avr. 2026"),
    ("avril 2021 - décembre 2021 (9 mois)", "Avr. 2021 – Déc. 2021 (9 mois)"),
    ("fin 2023 à 2024 (consultant)", "Fin 2023 – 2024 (consultant)"),
    ("Été 2019", "Été 2019"),  # illisible : laissé tel quel
])
def test_dates_use_one_french_format(raw, expected):
    assert format_date_text(raw) == expected


def test_placeholders_and_empty_parentheses_are_never_kept():
    data = _cv(
        formations=[
            {"date": "Non spécifié", "degree": "Licence de Droit", "school": "Non spécifié"},
            {"date": "2015", "degree": "", "school": "École de commerce ()"},
        ],
        experiences=[_exp("2001", company="Non spécifié"), _exp("Période non spécifiée", company="Acme")],
        languages=[{"name": "Anglais", "level": "N/A"}],
    )

    out = finalize_cv_content(data)

    assert out["formations"][0] == {"date": "", "degree": "Licence de Droit", "school": ""}
    assert out["formations"][1]["school"] == "École de commerce"
    assert out["experiences"][0]["company_highlight"] == ""
    assert out["languages"][0]["level"] == ""
    assert find_placeholders(out) == []
    assert "placeholder_removed" in _codes(out)


def test_inconnu_inside_a_sentence_is_content():
    text = "Dashboard météo applicative : soleil (Up), nuage (Down), point d’interrogation (Inconnu)."
    out = finalize_cv_content(_cv(experiences=[_exp("2020", content=[text])]))

    assert out["experiences"][0]["sections"][0]["content"] == [text]


def test_experiences_are_sorted_most_recent_first_current_job_on_top():
    data = _cv(experiences=[
        _exp("09/2025 – 09/2026", company="B"),
        _exp("01/2025 – 09/2025", company="C"),
        _exp("11/2018 – 02/2020", company="D"),
        _exp("12/2018 – Aujourd'hui", company="A"),
    ])

    out = finalize_cv_content(data)

    assert [e["company_highlight"] for e in out["experiences"]] == ["A", "B", "C", "D"]
    assert "experiences_reordered" in _codes(out)
    assert not experiences_out_of_order(out)


def test_single_month_heading_the_list_reads_as_current_position():
    data = _cv(experiences=[_exp("04/2025", company="A"), _exp("10/2022 à 10-2025", company="B"), _exp("02/2021 – 10/2022", company="C")])

    out = finalize_cv_content(data)

    assert [e["company_highlight"] for e in out["experiences"]] == ["A", "B", "C"]


def test_unreadable_date_leaves_the_order_and_warns():
    data = _cv(experiences=[_exp("2018 – 2019", company="B"), _exp("Été 2019", company="X"), _exp("2020 – 2022", company="A")])

    out = finalize_cv_content(data)

    assert [e["company_highlight"] for e in out["experiences"]] == ["B", "X", "A"]
    assert "experience_order_unverified" in _codes(out)


def test_repeated_experience_header_is_merged():
    data = _cv(experiences=[
        _exp("04/2017 – 05/2019", content=["Domaine prévoyance"], heading="Domaines fonctionnels"),
        _exp("04/2017 – 05/2019", content=["Recette des évolutions"], heading="Missions clés"),
    ])

    out = finalize_cv_content(data)

    assert len(out["experiences"]) == 1
    assert [s["heading"] for s in out["experiences"][0]["sections"]] == ["Domaines fonctionnels", "Missions clés"]


def test_company_field_sentence_goes_to_context():
    company = "Acme Énergie | Mission réalisée via W Hub, Paris — Administration fonctionnelle de la facturation électronique"
    out = finalize_cv_content(_cv(experiences=[_exp("2026", company=company)]))

    exp = out["experiences"][0]
    assert exp["company_highlight"] == "Acme Énergie"
    assert exp["sections"][0]["heading"] == "Contexte"
    assert exp["sections"][0]["content"][0].startswith("Mission réalisée via W Hub")


def test_company_name_in_capitals_is_not_split():
    company = "GROUPE BANQUE MUTUELLE – INFORMATIQUE"
    out = finalize_cv_content(_cv(experiences=[_exp("2026", company=company)]))

    assert out["experiences"][0]["company_highlight"] == company


def test_page_furniture_bullets_and_typography_are_cleaned():
    data = _cv(
        experiences=[_exp("2020", content=[
            "o Utilisation du SDK pour le stockage",
            "-> Développement des fonctions serverless",
            "Page 2 sur 7",
            "Recueil des besoins métiers.Cette approche réduit les délais,",
            "L ead Product Designer sur un SaaS médical",
            "Intégration dans les di érents SI.",
        ])],
        skills=[{"category": "Outils", "items": ["Jira", "Ines", "Analyste fonctionnelle Page 1", "D O S S I E R  D E  C O M P É T E N C E S"]}],
    )

    out = finalize_cv_content(data, furniture_lines=["Dernière mise à jour le 1er octobre 2025"])

    assert out["experiences"][0]["sections"][0]["content"] == [
        "Utilisation du SDK pour le stockage",
        "Développement des fonctions serverless",
        "Recueil des besoins métiers. Cette approche réduit les délais",
        "Lead Product Designer sur un SaaS médical",
        "Intégration dans les différents SI.",
    ]
    assert out["skills"][0]["items"] == ["Jira"]
    assert {"page_furniture_removed", "skill_item_removed", "text_repaired"} <= set(_codes(out))


def test_description_pipes_become_middots():
    out = finalize_cv_content(_cv(description="Business Analyst|Chef de projet"))

    assert out["description"] == "Business Analyst · Chef de projet"
    assert any(w["code"] == "description_too_short" for w in content_qa_warnings(out))


SOURCE = """Monitoring & Observabilité
Superviser les APIs : temps de réponse, erreurs et
disponibilité
Analyser les incidents
Refonte UX de plusieurs sections du site web, avec une réflexion sur la structure.
TAD / OD (architecture diagrams in draw.io) with system, network and storage services
Expert Métier Responsable du Service Production – Souscription puis Sous-Directeur
4 DATA CENTERS, Chassis Synergy 480, Dell, Cisco UCS, Suite VMware vRealize
(vROPS, VRLI, vRA), HCI, vSAN clusters étendus, One View, Nutanix(
metro cluster), volumétrie : 3000 ESXi, 50000 VMs.
"""


def test_cut_texts_are_repaired_from_the_source():
    data = _cv(experiences=[
        _exp("2024 – 2026", role="Expert Métier Responsable du Service Production – Souscripti", content=[
            "Superviser les APIs : temps de réponse, erreurs et",
            "Refonte UX de plusieurs sections du, avec une réflexion sur la structure.",
            "TAD / OD (architecture diagrams in ) with system, network and storage services",
            "4 DATA CENTERS, Chassis Synergy 480, Dell, Cisco UCS, Suite VMware vRealize",
            "(vROPS, VRLI, vRA), HCI, vSAN clusters étendus, One View, Nutanix(",
            "metro cluster), volumétrie: 3000 ESXi, 50000 VMs.",
        ]),
    ])

    out = finalize_cv_content(data, SOURCE)

    exp = out["experiences"][0]
    assert exp["role"].endswith("– Souscription")
    assert exp["sections"][0]["content"] == [
        "Superviser les APIs : temps de réponse, erreurs et disponibilité",
        "Refonte UX de plusieurs sections du site web, avec une réflexion sur la structure.",
        "TAD / OD (architecture diagrams in draw.io) with system, network and storage services",
        "4 DATA CENTERS, Chassis Synergy 480, Dell, Cisco UCS, Suite VMware vRealize (vROPS, VRLI, vRA), HCI, "
        "vSAN clusters étendus, One View, Nutanix(metro cluster), volumétrie: 3000 ESXi, 50000 VMs.",
    ]
    assert find_truncated_texts(out) == []


def test_short_table_cells_are_not_glued():
    source = "Service Now, Power BI, Active directory, Office 365\nentre 15 et 25 onboardings par jour\n"
    content = ["Service Now, Power BI, Active directory, Office 365", "entre 15 et 25 onboardings par jour"]

    out = finalize_cv_content(_cv(experiences=[_exp("2020", content=content)]), source)

    assert out["experiences"][0]["sections"][0]["content"] == content


@pytest.mark.parametrize("text, reason", [
    ("Superviser les APIs : temps de réponse, erreurs et", "fin_sur_mot_outil"),
    ("Recueil des besoins métiers (Finance", "parenthese_ouverte"),
    ("Refonte UX de plusieurs sections du, avec une réflexion", "mot_manquant"),
    ("HLD, LLD (architecture diagrams in ), code", "mot_manquant"),
    ("Conception de la communication (plaquettes, tarifs),", "fin_sur_virgule"),
    ("3768 tickets / an", None),
    ("Services du site (ex: Virtual Try On, Beauty Genius)", None),
    ("Pilotage du run et des évolutions.", None),
])
def test_truncation_detection(text, reason):
    assert looks_truncated(text) == reason


def test_qa_warnings_future_date_english_content_and_company_sentence():
    english = [
        "Design of the target architecture for the client and the migration of the legacy platform to the cloud with the teams",
        "Workshops with the security, network and business teams to build the architecture documents for the program",
    ] * 3
    data = _cv(experiences=[
        _exp("Juin 2026 – Déc. 2026", content=english,
             company="Caisse de retraite des agents, Paris — Optimisation du pilotage budgétaire et des reportings mensuels"),
    ])

    codes = {w["code"] for w in content_qa_warnings(data, today=date(2026, 11, 10))}

    assert {"future_end_date", "content_language_not_french", "company_field_sentence"} <= codes


def test_finishing_is_idempotent():
    data = _cv(experiences=[_exp("12/2018 – Present", company="A"), _exp("2020 – 2021", company="B")],
               formations=[{"date": "Non spécifié", "degree": "Master", "school": "IAE"}])
    once = finalize_cv_content(data, SOURCE)
    twice = finalize_cv_content(once, SOURCE)

    assert twice == once


def test_list_introduction_gets_its_colon_back_and_long_wrapped_line_is_restored():
    source = (
        "Réalisation des audits, principalement sur :\no La sécurité des applications\n"
        "Entretien avec le chef de projet afin de mener l’audit sur des\n"
        "thématiques transverses (sécurité physique, cartographie, authentification, administration, MCO/MCS …)\n"
    )
    data = _cv(experiences=[_exp("2020", content=[
        "Réalisation des audits, principalement sur", "La sécurité des applications",
        "Entretien avec le chef de projet afin de mener l’audit sur des",
    ])])

    out = finalize_cv_content(data, source)

    assert out["experiences"][0]["sections"][0]["content"] == [
        "Réalisation des audits, principalement sur :",
        "La sécurité des applications",
        "Entretien avec le chef de projet afin de mener l’audit sur des thématiques transverses "
        "(sécurité physique, cartographie, authentification, administration, MCO/MCS …)",
    ]
