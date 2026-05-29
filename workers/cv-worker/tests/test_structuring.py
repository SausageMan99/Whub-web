import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.structuring import (
    compact_extracted_text,
    assert_no_contact_in_json,
    validate_source_fidelity,
    build_whub_json,
    _extract_json,
    StructuringError,
    REQUIRED_TOP_LEVEL_KEYS,
    normalize_candidate_first_name,
    resolve_synthesis_mode,
    infer_forbidden_candidate_identity_terms,
    apply_client_synthesis_policy,
    _hermes_prompt,
    _source_gate_structured_data,
    split_cv_text_into_blocks,
    find_numbered_placeholder_repetitions,
)


class TestCompactExtractedText:
    def test_dedup_blank_lines(self):
        source = "Line 1\n\n\n\nLine 2\n\n\nLine 3"
        result = compact_extracted_text(source)
        assert "\n\n\n" not in result
        assert result == "Line 1\n\nLine 2\n\nLine 3"

    def test_preserves_non_empty_lines(self):
        source = "A\nB\nC"
        assert compact_extracted_text(source) == "A\nB\nC"

    def test_strips_trailing_whitespace_per_line(self):
        source = "  spaced out  \n\n  another  "
        assert compact_extracted_text(source) == "spaced out\n\nanother"

    def test_normalizes_crlf(self):
        source = "A\r\nB\rC"
        assert compact_extracted_text(source) == "A\nB\nC"


class TestLongCVSplitting:
    def test_repairs_oussama_style_contact_noise_and_date_stubs(self):
        source = """
Oussama ASSAOUI
Technical Leader RPA/IA
2019 - 2020
2016 - 2019
Université Gustave Eiffel
M2 en Informatique
EXPÉRIENCES PROFESSIONNELLES
+33 7 58 46 54 53
oussama.assaoui@example.com
https://www.linkedin.com/in/oussama-assaoui/
FORMATION
07/2022 – 01/2024     Software Engineer - CDI chez BNP Paribas - France
Missions :
-
Conceptualiser, développer et mettre en œuvre les robots logiciels pour automatiser les processus métier clés.
Livrables clés :
-
Déploiement de 4 nouveaux robots RPA en production.
01/2024 – Aujourd’hui     Consultant RPA Senior – Freelance chez EDF - France
Missions :
-
Contribuer activement à la feuille de route RPA d’EDF.
2019
2018
CERTIFICATIONS
COMPÉTENCES
•   RPA :
Blue Prism
"""

        blocks = split_cv_text_into_blocks(source)
        texts = [block["text"] for block in blocks]

        assert not any("+33" in text or "linkedin" in text.lower() for text in texts)
        assert not any(text.strip() in {"2019", "2018"} for text in texts)
        assert any(block["kind"] == "experience" and "Software Engineer - CDI chez BNP Paribas" in block["text"] and "Conceptualiser" in block["text"] for block in blocks)
        assert not any(block["kind"] == "education" and "Software Engineer - CDI" in block["text"] for block in blocks)

    def test_suite_numbered_categories_are_not_placeholder_repetitions(self):
        assert find_numbered_placeholder_repetitions(["Autres — suite 2", "Autres — suite 3", "Autres — suite 4"]) == []


class TestAssertNoContactInJson:
    def test_raises_on_email(self):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        data["experiences"] = [{"date": "2024", "role": "Dev", "sections": [{"heading": "Contact", "content": ["jean@example.com"]}]}]
        with pytest.raises(StructuringError, match="Coordonnées"):
            assert_no_contact_in_json(data)

    def test_raises_on_linkedin(self):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        data["description"] = "Profil linkedin/in/jean"
        with pytest.raises(StructuringError, match="Coordonnées"):
            assert_no_contact_in_json(data)

    def test_raises_on_phone(self):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        data["experiences"] = [{"date": "2024", "role": "Dev", "sections": [{"heading": "Contact", "content": ["+33 6 12 34 56 78"]}]}]
        with pytest.raises(StructuringError, match="Coordonnées"):
            assert_no_contact_in_json(data)

    def test_raises_on_github(self):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        data["skills"] = [{"category": "Web", "items": ["github.com/jean"]}]
        with pytest.raises(StructuringError, match="Coordonnées"):
            assert_no_contact_in_json(data)

    def test_passes_without_contact(self):
        data = {
            "name": "JEAN",
            "title": "Dev",
            "formations": [{"date": "2020", "degree": "Master", "school": "Uni"}],
            "skills": [{"category": "Langages", "items": ["Python"]}],
            "experiences": [{"date": "2024", "role": "Dev", "sections": []}],
        }
        assert_no_contact_in_json(data)  # no raise


class TestSourceFidelity:
    def test_rejects_oussama_style_structural_fragments_before_render(self):
        source = """
Oussama
07/2022 – 01/2024
Software Engineer - CDI
BNP Paribas - France
Missions
Conceptualiser, développer et mettre en œuvre les robots logiciels pour automatiser les processus métier clés.
09/2020 – 07/2022
Tech Lead RPA - CDI chez STALLERGENES GREER - France
2018
"""
        data = {
            "name": "OUSSAMA",
            "title": "Technical Leader RPA/IA",
            "formations": [
                {"date": "07/2022 – 01/2024", "degree": "Software Engineer - CDI", "school": "BNP Paribas - France"},
                {"date": "2018", "degree": "", "school": ""},
            ],
            "skills": [],
            "experiences": [
                {"date": "", "role": "", "company_highlight": "", "sections": [{"heading": "Missions", "content": ["Conceptualiser, développer et mettre en œuvre les robots logiciels pour automatiser les processus métier clés."]}]},
                {"date": "09/2020 – 07/2022", "role": "Tech Lead RPA - CDI chez STALLERGENES GREER - France", "company_highlight": "STALLERGENES GREER", "sections": []},
                {"date": "2018", "role": "", "company_highlight": "", "sections": []},
            ],
        }

        with pytest.raises(StructuringError) as exc:
            validate_source_fidelity(source, data, forbidden_identity_terms=[])

        message = str(exc.value)
        assert "experience_misclassified_as_formation" in message
        assert "headerless_experience_sections" in message
        assert "experience_header_without_body" in message
        assert "empty_experience_date_stub" in message

    def test_source_fidelity_ignores_pdf_page_markers_inside_source_sentence(self):
        source = """
DIGITAL SEEDER
UI - UX Designer
mars 2020 - mars 2021
Pour un client dans le domaine du football, j'ai travaillé sur la conception
d'une application mobile de type réseau social axée autour du football. Le
projet a nécessité la création de plus de 100 écrans, y compris des wireframes
détaillés et des maquettes haute-fidélité. J'ai également été responsable de
Page 2 of 4
l'identité visuelle complète du produit et de l'accompagnement client pour
définition du besoin.
"""
        data = {
            "name": "GAËL",
            "title": "UI - UX Designer",
            "formations": [],
            "skills": [],
            "experiences": [{
                "date": "mars 2020 - mars 2021",
                "role": "UI - UX Designer chez DIGITAL SEEDER",
                "company_highlight": "DIGITAL SEEDER",
                "sections": [{"heading": "Missions clés", "content": [
                    "Pour un client dans le domaine du football, j'ai travaillé sur la conception d'une application mobile de type réseau social axée autour du football. Le projet a nécessité la création de plus de 100 écrans, y compris des wireframes détaillés et des maquettes haute-fidélité. J'ai également été responsable de l'identité visuelle complète du produit et de l'accompagnement client pour définition du besoin."
                ]}],
            }],
        }

        validate_source_fidelity(source, data, forbidden_identity_terms=[])

    def test_rejects_numbered_placeholder_repeated_bullets(self):
        data = {
            "name": "ZAHIA",
            "title": "Chef de projet",
            "formations": [],
            "skills": [],
            "experiences": [{
                "date": "2024",
                "role": "Chef de projet",
                "sections": [{"heading": "Missions clés", "content": [
                    "Analyse des besoins assurance 1",
                    "Analyse des besoins assurance 2",
                    "Analyse des besoins assurance 3",
                ]}],
            }],
        }

        with pytest.raises(StructuringError, match="placeholder|numérot"):
            validate_source_fidelity("CV source sans ces placeholders", data)

    def test_rejects_company_highlight_absent_from_source(self):
        source = "Zahia\nJuin 2023 – A ce jour\nChef de projet | GROUPE KLESIA | Protection sociale"
        data = {
            "name": "ZAHIA",
            "title": "Chef de projet",
            "formations": [],
            "skills": [],
            "experiences": [{
                "date": "Mars 2026 – à ce jour",
                "role": "Chef de projet | Mutuelle GSMC | Protection sociale",
                "company_highlight": "Mutuelle GSMC",
                "sections": [],
            }],
        }

        with pytest.raises(StructuringError, match="source"):
            validate_source_fidelity(source, data, forbidden_identity_terms=[])

    def test_rejects_experience_date_absent_from_source(self):
        source = "Zahia\nJuin 2023 – A ce jour\nChef de projet | GROUPE KLESIA | Protection sociale"
        data = {
            "name": "ZAHIA",
            "title": "Chef de projet",
            "formations": [],
            "skills": [],
            "experiences": [{
                "date": "Mars 2026 – à ce jour",
                "role": "Chef de projet | GROUPE KLESIA | Protection sociale",
                "company_highlight": "GROUPE KLESIA",
                "sections": [],
            }],
        }

        with pytest.raises(StructuringError, match="date.*source|source.*date"):
            validate_source_fidelity(source, data, forbidden_identity_terms=[])

    def test_rejects_role_fact_absent_from_source_even_without_company_highlight(self):
        source = "Zahia\nJuin 2023 – A ce jour\nChef de projet | GROUPE KLESIA | Protection sociale"
        data = {
            "name": "ZAHIA",
            "title": "Chef de projet",
            "formations": [],
            "skills": [],
            "experiences": [{
                "date": "Juin 2023 – à ce jour",
                "role": "Chef de projet | Mutuelle GSMC | Protection sociale",
                "company_highlight": "",
                "sections": [],
            }],
        }

        with pytest.raises(StructuringError, match="rôle|role|source"):
            validate_source_fidelity(source, data, forbidden_identity_terms=[])

    def test_rejects_full_name_display_in_renderer_json(self):
        source = "Zahia Aris\nChef de projet"
        data = {
            "name": "ZAHIA ARIS",
            "title": "Chef de projet",
            "formations": [],
            "skills": [],
            "experiences": [],
        }

        with pytest.raises(StructuringError, match="nom complet|full_name"):
            validate_source_fidelity(source, data, forbidden_identity_terms=[])

    def test_rejects_candidate_surname_outside_name_field(self):
        source = "Jean Dupont\nDéveloppeur\n2024 Mission\nConstruire les robots logiciels."
        data = {
            "name": "JEAN",
            "title": "Développeur",
            "description": "Jean Dupont est développeur senior.",
            "formations": [],
            "skills": [],
            "experiences": [{"date": "2024", "role": "Mission", "sections": [{"heading": "Missions clés", "content": ["Construire les robots logiciels."]}]}],
        }

        assert infer_forbidden_candidate_identity_terms(source, "Jean Dupont") == ["Dupont"]
        with pytest.raises(StructuringError, match="identité|identity|Dupont|Nom de famille"):
            validate_source_fidelity(source, data, forbidden_identity_terms=["Dupont"])

    def test_does_not_infer_company_header_as_candidate_surname(self):
        source = """
Orange Business
Jean Dupont
Architecte
2024 Architecte | Orange Business
Piloter le projet.
"""
        data = {
            "name": "JEAN",
            "title": "Architecte",
            "formations": [],
            "skills": [],
            "experiences": [{"date": "2024", "role": "Architecte | Orange Business", "company_highlight": "Orange Business", "sections": [{"heading": "Missions clés", "content": ["Piloter le projet."]}]}],
        }

        assert infer_forbidden_candidate_identity_terms(source, "Jean") == ["Dupont"]
        validate_source_fidelity(source, data, forbidden_identity_terms=infer_forbidden_candidate_identity_terms(source, "Jean"))

    def test_empty_forbidden_identity_terms_do_not_fallback_to_company_header(self):
        source = """
Orange Business
Architecte
2024 Architecte | Orange Business
Piloter le projet.
"""
        data = {
            "name": "JEAN",
            "title": "Architecte",
            "formations": [],
            "skills": [],
            "experiences": [{"date": "2024", "role": "Architecte | Orange Business", "company_highlight": "Orange Business", "sections": [{"heading": "Missions clés", "content": ["Piloter le projet."]}]}],
        }

        assert infer_forbidden_candidate_identity_terms(source, "Jean") == []
        validate_source_fidelity(source, data, forbidden_identity_terms=[])

    def test_resolve_synthesis_mode_ignores_standard_without_explicit_short_instruction(self):
        assert resolve_synthesis_mode("standard", "", []) == "complete"
        assert resolve_synthesis_mode("urgent", "Mettre en avant la mission cible", []) == "complete"

    def test_apply_client_synthesis_policy_does_not_condense_standard_without_explicit_flag(self):
        data = {
            "name": "JEAN",
            "title": "Dev",
            "formations": [],
            "skills": [],
            "experiences": [
                {"date": "2024", "role": "A", "sections": [{"heading": "Missions clés", "content": ["A1", "A2", "A3"]}]},
                {"date": "2023", "role": "B", "sections": [{"heading": "Missions clés", "content": ["B1", "B2", "B3"]}]},
                {"date": "2022", "role": "C", "sections": [{"heading": "Missions clés", "content": ["C1", "C2", "C3"]}]},
                {"date": "2021", "role": "D", "sections": [{"heading": "Missions clés", "content": ["D1", "D2", "D3"]}]},
                {"date": "2020", "role": "E", "sections": [{"heading": "Missions clés", "content": ["E1", "E2", "E3"]}]},
            ],
        }

        result = apply_client_synthesis_policy(data, "standard")

        assert result["synthesis_policy"]["mode"] == "complete"
        assert result["experiences"][4]["sections"][0]["heading"] == "Missions clés"
        assert result["experiences"][4]["sections"][0]["content"] == ["E1", "E2", "E3"]

    def test_rejects_synthetic_technical_environment_when_heading_absent_from_source(self):
        source = """
Responsable du Domaine Applicatif SI Groupe
Novembre 2024 - Aujourd'hui - TEXDECOR GROUP
Gestion de l'ERP D365 Microsoft, WMS Sage, TMS, interapplicatif, data et alimentation web, PDP facture...
"""
        data = {
            "name": "NICOLAS",
            "title": "Responsable du Domaine Applicatif SI Groupe",
            "formations": [],
            "skills": [],
            "experiences": [{
                "date": "Novembre 2024 - Aujourd'hui",
                "role": "Responsable du Domaine Applicatif SI Groupe",
                "company_highlight": "TEXDECOR GROUP",
                "sections": [{"heading": "Environnement technique", "content": "ERP D365 Microsoft, WMS Sage, TMS, interapplicatif, data et alimentation web, PDP facture"}],
            }],
        }

        with pytest.raises(StructuringError, match="Environnement technique|synthetic_technical_environment|copier-coller|reformulation"):
            validate_source_fidelity(source, data, forbidden_identity_terms=[])

    def test_accepts_thorez_source_paragraph_without_synthetic_environment(self):
        source = """
Responsable du Domaine Applicatif SI Groupe
Novembre 2024 - Aujourd'hui - TEXDECOR GROUP
Gestion de l'ERP D365 Microsoft, WMS Sage, TMS, interapplicatif, data et alimentation web, PDP facture...
"""
        data = {
            "name": "NICOLAS",
            "title": "Responsable du Domaine Applicatif SI Groupe",
            "formations": [],
            "skills": [],
            "experiences": [{
                "date": "Novembre 2024 - Aujourd'hui",
                "role": "Responsable du Domaine Applicatif SI Groupe",
                "company_highlight": "TEXDECOR GROUP",
                "sections": [{"heading": "Missions clés", "content": ["Gestion de l'ERP D365 Microsoft, WMS Sage, TMS, interapplicatif, data et alimentation web, PDP facture..."]}],
            }],
        }

        validate_source_fidelity(source, data, forbidden_identity_terms=[])

    def test_apply_client_synthesis_policy_preserves_thorez_source_skill_categories(self):
        data = {
            "name": "NICOLAS",
            "title": "Responsable du Domaine Applicatif SI Groupe",
            "formations": [],
            "skills": [
                {"category": "Compétences et outils", "items": [
                    "Management d'équipe",
                    "Anglais professionnel (835 TOEIC - 2015)",
                    "Office, Excel (VBA), MS Project, Visio, AutoCAD, Catia",
                    "ERP - AS400 DB2 – SAP - ORACLE - D365",
                    "GMAO (Coswin, twimm, Corim, SAP, Planon, AS400)",
                    "SAP fonctionnel (module gestion de production, planification, gestion des stocks et achats)",
                    "Outils de suivi de développements (Jira, HPALM)",
                ]},
                {"category": "Processus métiers", "items": [
                    "Gestion de projets informatiques",
                    "ERP, GMAO, WMS, TMS, SIRH",
                    "Applications Web & mobile",
                    "Comptabilité Finance - ERP",
                    "Controle de gestion & décisionnel",
                    "Supply chain",
                    "Gestion de production",
                ]},
            ],
            "experiences": [],
        }

        result = apply_client_synthesis_policy(data, "complete")

        assert [skill["category"] for skill in result["skills"]] == ["Compétences et outils", "Processus métiers"]
        assert "Autres — suite" not in json.dumps(result, ensure_ascii=False)

    def test_source_gate_keeps_only_thorez_source_skill_categories_when_present(self):
        source = """
Processus métiers :
✓Gestion de projets informatiques
Compétences et outils :
✓Management d'équipe
✓Office, Excel (VBA), MS Project, Visio, AutoCAD, Catia
Loisirs :
✓Moto
✓Cuisine
#Gestion de portefeuille projets
"""
        data = {
            "name": "NICOLAS",
            "title": "Responsable du Domaine Applicatif SI Groupe",
            "formations": [],
            "skills": [
                {"category": "Mots-clés", "items": ["#Gestion de portefeuille projets"]},
                {"category": "Processus métiers", "items": ["Gestion de projets informatiques"]},
                {"category": "Compétences et outils", "items": ["Management d'équipe", "Office, Excel (VBA), MS Project, Visio, AutoCAD, Catia"]},
                {"category": "Autres", "items": ["Moto", "Cuisine"]},
            ],
            "experiences": [],
        }

        result = _source_gate_structured_data(data, source)

        assert [skill["category"] for skill in result["skills"]] == ["Processus métiers", "Compétences et outils"]
        assert "Mots-clés" not in json.dumps(result, ensure_ascii=False)
        assert "Autres" not in json.dumps(result, ensure_ascii=False)


    def test_source_gate_preserves_autres_when_items_are_real_source_achievements(self):
        source = """
Processus métiers :
✓Gestion de projets informatiques
Compétences et outils :
✓Management d'équipe
Exemples de réalisations professionnelles
:
✓Gestion d'un SI d'une usine pharmaceutique (+500 employés)
✓Conception, développement et mise en place d’une application de suivi de prestations (85 000 logements) via app mobile & QR codes installés dans les parties communes (#10 000 QR codes suivis) [Point Of Control Vilogia]
Loisirs :
✓Moto
"""
        data = {
            "name": "NICOLAS",
            "title": "Responsable du Domaine Applicatif SI Groupe",
            "formations": [],
            "skills": [
                {"category": "Processus métiers", "items": ["Gestion de projets informatiques"]},
                {"category": "Compétences et outils", "items": ["Management d'équipe"]},
                {"category": "Autres", "items": [
                    "Gestion d'un SI d'une usine pharmaceutique (+500 employés)",
                    "Conception, développement et mise en place d’une application de suivi de prestations (85 000 logements) via app mobile & QR codes installés dans les parties communes (#10 000 QR codes suivis) [Point Of Control Vilogia]",
                    "Moto",
                ]},
            ],
            "experiences": [],
        }

        result = _source_gate_structured_data(data, source)

        assert [skill["category"] for skill in result["skills"]] == [
            "Processus métiers",
            "Compétences et outils",
            "Exemples de réalisations professionnelles",
        ]
        rendered = json.dumps(result, ensure_ascii=False)
        assert "usine pharmaceutique" in rendered
        assert "Point Of Control Vilogia" in rendered
        assert "Moto" not in rendered

    def test_hermes_prompt_forbids_synthetic_technical_environment_and_typo_fixes(self):
        prompt = _hermes_prompt("CV source", "", [], "Nicolas")

        assert "Ne déduis jamais un environnement technique" in prompt
        assert "N’utilise `Environnement technique`" in prompt
        assert "Ne corrige pas les typos" in prompt
        assert "Environnement technique` quand l'information existe" not in prompt
        assert "Corrige seulement les erreurs évidentes" not in prompt

    def test_rejects_rewritten_experience_bullets_even_when_topic_matches_source(self):
        source = """
Oussama ASSAOUI
Technical Leader RPA/IA
07/2022 – 01/2024 Software Engineer - CDI chez BNP Paribas - France
Conceptualiser, développer et mettre en œuvre les robots logiciels pour automatiser les processus métier clés.
Participer activement aux réunions avec les parties prenantes, fournissant des mises à jour régulières sur l'avancement des projets RPA, des démonstrations sur les résultats obtenus et les perspectives d'amélioration.
"""
        data = {
            "name": "OUSSAMA",
            "title": "Technical Leader RPA/IA",
            "formations": [],
            "skills": [],
            "experiences": [{
                "date": "07/2022 – 01/2024",
                "role": "Software Engineer - CDI chez BNP Paribas - France",
                "company_highlight": "BNP Paribas - France",
                "sections": [{"heading": "Missions clés", "content": [
                    "Conceptualiser, développer et mettre en œuvre des robots logiciels pour automatiser les processus métier clés.",
                    "Participer activement aux réunions avec les parties prenantes, fournir des mises à jour régulières sur l'avancement des projets RPA.",
                ]}],
            }],
        }

        with pytest.raises(StructuringError, match="reformul|copier-coller|fidélité|fidelite"):
            validate_source_fidelity(source, data, forbidden_identity_terms=[])

    def test_rejects_synthesis_whub_without_explicit_short_instruction(self):
        source = "Jean\nDéveloppeur\n2024 Mission\nConstruire les robots logiciels."
        data = {
            "name": "JEAN",
            "title": "Développeur",
            "formations": [],
            "skills": [],
            "experiences": [{"date": "2024", "role": "Mission", "sections": [{"heading": "Synthèse mission", "content": ["Synthèse W hub: mission condensée."]}]}],
        }

        with pytest.raises(StructuringError, match="Synthèse|synthèse|synthese"):
            validate_source_fidelity(source, data, forbidden_identity_terms=[])

    def test_title_must_be_source_backed_or_safe_fallback(self):
        source = "Oussama\nTechnical Leader RPA/IA\n2024 Mission"
        data = {"name": "OUSSAMA", "title": "Chef de projet RPA/IA", "formations": [], "skills": [], "experiences": []}

        with pytest.raises(StructuringError, match="Titre|title|source"):
            validate_source_fidelity(source, data, forbidden_identity_terms=[])

    def test_oussama_fixture_has_zero_missing_experience_items(self):
        fixture_dir = Path(__file__).parent / "fixtures"
        source = (fixture_dir / "oussama_source.txt").read_text(encoding="utf-8")
        data = json.loads((fixture_dir / "oussama_structured_faithful.json").read_text(encoding="utf-8"))

        validate_source_fidelity(source, data)

    def test_build_whub_json_default_does_not_condense_or_rewrite_source_content(self):
        source = """
Oussama ASSAOUI
Technical Leader RPA/IA
2020 - 2021 Mission A
Rédiger la documentation complète des robots développés.
2021 - 2022 Mission B
Qualifier les demandes de robotisation des processus d’exploitation.
2022 - 2023 Mission C
Développer les robots logiciels Blue Prism.
2023 - 2024 Mission D
Participer aux réunions avec les parties prenantes.
2024 - Aujourd’hui Mission E
Contribuer à la feuille de route RPA.
"""
        data = {
            "name": "Oussama",
            "title": "Technical Leader RPA/IA",
            "formations": [],
            "skills": [],
            "experiences": [
                {"date": "2020 - 2021", "role": "Mission A", "sections": [{"heading": "Missions clés", "content": ["Rédiger la documentation complète des robots développés."]}]},
                {"date": "2021 - 2022", "role": "Mission B", "sections": [{"heading": "Missions clés", "content": ["Qualifier les demandes de robotisation des processus d’exploitation."]}]},
                {"date": "2022 - 2023", "role": "Mission C", "sections": [{"heading": "Missions clés", "content": ["Développer les robots logiciels Blue Prism."]}]},
                {"date": "2023 - 2024", "role": "Mission D", "sections": [{"heading": "Missions clés", "content": ["Participer aux réunions avec les parties prenantes."]}]},
                {"date": "2024 - Aujourd’hui", "role": "Mission E", "sections": [{"heading": "Missions clés", "content": ["Contribuer à la feuille de route RPA."]}]},
            ],
        }

        def runner(prompt: str, timeout: int):
            return 0, json.dumps(data, ensure_ascii=False), ""

        result = build_whub_json(source, "", [], "Oussama", hermes_runner=runner)

        assert result["synthesis_policy"]["mode"] == "complete"
        assert result["experiences"][3]["sections"][0]["heading"] == "Missions clés"
        assert result["experiences"][3]["sections"][0]["content"] == ["Participer aux réunions avec les parties prenantes."]
        assert "Synthèse mission" not in json.dumps(result, ensure_ascii=False)


class TestExtractJson:
    def test_extracts_fenced_json(self):
        raw = '```json\n{"name":"A","title":"B","formations":[],"skills":[],"experiences":[]}\n```'
        result = _extract_json(raw)
        assert result["name"] == "A"

    def test_extracts_bare_json(self):
        raw = 'Some text before\n{"name":"A","title":"B","formations":[],"skills":[],"experiences":[]}\nAfter'
        result = _extract_json(raw)
        assert result["name"] == "A"

    def test_raises_when_required_keys_missing(self):
        raw = '{"name":"A","title":"B","formations":[],"skills":[]}'  # missing experiences
        with pytest.raises(StructuringError, match="clés manquantes"):
            _extract_json(raw)

    def test_defaults_missing_formations_to_empty_list(self):
        raw = '{"name":"A","title":"B","skills":[],"experiences":[]}'
        result = _extract_json(raw)
        assert result["formations"] == []

    def test_raises_when_experiences_not_list(self):
        raw = '{"name":"A","title":"B","formations":[],"skills":[],"experiences":"nope"}'
        with pytest.raises(StructuringError, match="doit être une liste"):
            _extract_json(raw)

    def test_raises_on_invalid_json(self):
        raw = "not json at all"
        with pytest.raises(StructuringError, match="JSON exploitable"):
            _extract_json(raw)


class TestBuildWHubJson:
    def _make_runner(self, data: dict):
        def runner(prompt: str, timeout: int):
            return 0, json.dumps(data, ensure_ascii=False), ""
        return runner

    def test_build_whub_json_returns_all_required_keys(self):
        data = {
            "name": "Jean",
            "title": "Architecte",
            "formations": [{"date": "2020", "degree": "Master", "school": "Uni"}],
            "skills": [{"category": "Cloud", "items": ["AWS"]}],
            "experiences": [{"date": "2024", "role": "Lead", "sections": [{"heading": "Missions clés", "content": ["Piloter l'architecture cible."]}]}],
        }
        result = build_whub_json("Jean\nArchitecte\n2024 Lead\nPiloter l'architecture cible.\nsome cv text\n" * 20, "", [], "Jean", hermes_runner=self._make_runner(data))
        assert REQUIRED_TOP_LEVEL_KEYS.issubset(set(result.keys()))
        assert result["name"] == "JEAN"
        assert result["title"] == "Architecte"

    def test_build_whub_json_applies_candidate_first_name(self):
        data = {
            "name": "Wrong",
            "title": "Dev",
            "formations": [],
            "skills": [],
            "experiences": [],
        }
        result = build_whub_json("cv text\n" * 100, "", [], "Pierre", hermes_runner=self._make_runner(data))
        assert result["name"] == "PIERRE"

    def test_candidate_first_name_normalization_removes_surname_but_keeps_hyphenated_first_name(self):
        assert normalize_candidate_first_name("ZAHIA ARIS") == "ZAHIA"
        assert normalize_candidate_first_name(" Jean-Pierre Dupont ") == "JEAN-PIERRE"

    def test_build_whub_json_reapplies_first_name_after_synthesis_policy(self):
        data = {
            "name": "ZAHIA ARIS",
            "title": "Cheffe de projet",
            "formations": [],
            "skills": [],
            "experiences": [{"date": "2024", "role": "Mission", "sections": [{"heading": "Missions clés", "content": ["Assurer la coordination projet."]}]}],
        }
        result = build_whub_json("Zahia Aris\nCheffe de projet\n2024 Mission\nAssurer la coordination projet.\ncv text\n" * 20, "", [], "ZAHIA ARIS", hermes_runner=self._make_runner(data))
        assert result["name"] == "ZAHIA"

    def test_build_whub_json_raises_on_hermes_failure(self):
        def bad_runner(prompt: str, timeout: int):
            return 1, "", "Hermes crashed"

        with pytest.raises(StructuringError, match="Hermes"):
            build_whub_json("cv text\n" * 100, "", [], hermes_runner=bad_runner)

    def test_build_whub_json_raises_on_contact_in_response(self):
        data = {
            "name": "Jean",
            "title": "Dev",
            "formations": [],
            "skills": [],
            "experiences": [{"date": "2024", "role": "Dev", "sections": [{"heading": "Contact", "content": ["jean@example.com"]}]}],
        }
        with pytest.raises(StructuringError, match="Coordonnées"):
            build_whub_json("cv text\n" * 100, "", [], hermes_runner=self._make_runner(data))

    def test_build_whub_json_uses_long_cv_mode_when_text_exceeds_threshold(self):
        calls = []

        def tracking_runner(prompt: str, timeout: int):
            calls.append(prompt)
            return 0, json.dumps({
                "name": "Jean", "title": "Dev",
                "formations": [], "skills": [], "experiences": [],
            }, ensure_ascii=False), ""

        long_text = "PROFIL\nJean architecte\n\nEXPÉRIENCES\n2022 ACME\n" + ("ligne acme\n" * 30) + "\n2021 BETA\n" + ("ligne beta\n" * 30)
        build_whub_json(long_text, "", [], "Jean", long_cv_threshold=80, hermes_runner=tracking_runner)
        assert len(calls) >= 2

    def test_build_whub_json_synthesis_mode_complete(self):
        data = {
            "name": "Jean", "title": "Dev",
            "formations": [], "skills": [], "experiences": [],
        }
        result = build_whub_json("cv text\n" * 100, "", [], hermes_runner=self._make_runner(data), synthesis_mode="complete")
        assert result["synthesis_policy"]["mode"] == "complete"

    def test_build_whub_json_switches_to_complete_when_instructions_forbid_compaction(self):
        data = {
            "name": "Zahia",
            "title": "Chef de projet",
            "formations": [],
            "skills": [],
            "experiences": [
                {"date": "2024", "role": "Mission A", "sections": [{"heading": "Missions clés", "content": ["A1", "A2", "A3"]}]},
                {"date": "2023", "role": "Mission B", "sections": [{"heading": "Missions clés", "content": ["B1", "B2", "B3"]}]},
                {"date": "2022", "role": "Mission C", "sections": [{"heading": "Missions clés", "content": ["C1", "C2", "C3"]}]},
                {"date": "2021", "role": "Mission D", "sections": [{"heading": "Missions clés", "content": ["D1", "D2", "D3"]}]},
                {"date": "2020", "role": "Mission E", "sections": [{"heading": "Missions clés", "content": ["E1", "E2", "E3"]}]},
            ],
        }

        result = build_whub_json(
            "Zahia\nChef de projet\n2024 Mission A\nA1\nA2\nA3\n2023 Mission B\nB1\nB2\nB3\n2022 Mission C\nC1\nC2\nC3\n2021 Mission D\nD1\nD2\nD3\n2020 Mission E\nE1\nE2\nE3",
            "Ne pas compacter, conserver le CV complet et fidèle",
            [],
            "Zahia",
            hermes_runner=self._make_runner(data),
        )

        assert result["synthesis_policy"]["mode"] == "complete"
        assert result["experiences"][4]["sections"][0]["content"] == ["E1", "E2", "E3"]

    def test_build_whub_json_default_preserves_five_experiences_without_condensing(self):
        data = {
            "name": "Zahia",
            "title": "Chef de projet",
            "formations": [],
            "skills": [],
            "experiences": [
                {"date": "2024", "role": "Mission A", "sections": [{"heading": "Missions clés", "content": ["A1", "A2", "A3"]}]},
                {"date": "2023", "role": "Mission B", "sections": [{"heading": "Missions clés", "content": ["B1", "B2", "B3"]}]},
                {"date": "2022", "role": "Mission C", "sections": [{"heading": "Missions clés", "content": ["C1", "C2", "C3"]}]},
                {"date": "2021", "role": "Mission D", "sections": [{"heading": "Missions clés", "content": ["D1", "D2", "D3"]}]},
                {"date": "2020", "role": "Mission E", "sections": [{"heading": "Missions clés", "content": ["E1", "E2", "E3"]}]},
            ],
        }

        result = build_whub_json(
            "Zahia\nChef de projet\n2024 Mission A\nA1\nA2\nA3\n2023 Mission B\nB1\nB2\nB3\n2022 Mission C\nC1\nC2\nC3\n2021 Mission D\nD1\nD2\nD3\n2020 Mission E\nE1\nE2\nE3",
            "",
            [],
            "Zahia",
            hermes_runner=self._make_runner(data),
        )

        assert result["synthesis_policy"]["mode"] == "complete"
        assert len(result["experiences"]) == 5
        assert result["experiences"][4]["sections"][0]["heading"] == "Missions clés"
        assert result["experiences"][4]["sections"][0]["content"] == ["E1", "E2", "E3"]

    def test_explicit_synthesis_instruction_enables_standard_condensation(self):
        assert resolve_synthesis_mode("complete", "Merci de faire une synthèse courte client", []) == "standard"
