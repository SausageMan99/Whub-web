from __future__ import annotations

from pathlib import Path

import fitz

from src.layout_packing import build_layout_packing_options
from src.qa import collect_page_layout_metrics, run_qa
from src.rendering import render_pdf


def _experience(index: int, bullet_count: int, *, long: bool = False) -> dict:
    suffix = " avec documentation détaillée des processus et indicateurs de suivi" if long else ""
    return {
        "date": f"20{24 - index} - 20{25 - index}",
        "role": f"CONSULTANT SI SYNTHÉTIQUE {index} CHEZ CLIENT {index}",
        "company_highlight": f"CLIENT {index}",
        "sections": [
            {
                "heading": "Missions",
                "content": [
                    f"Mission {index}.{bullet:02d} cadrage métier, ateliers, pilotage, recette et coordination transverse{suffix}"
                    for bullet in range(1, bullet_count + 1)
                ],
            },
            {
                "heading": "Environnement technique",
                "content": ["Jira", "Confluence", "SQL", "API REST"] if index <= 3 else ["Jira", "Excel"],
            },
        ],
    }


def _oussama_like_synthetic_cv() -> dict:
    return {
        "name": "OSSAMA",
        "title": "Consultant AMOA / Product Owner",
        "description": (
            "Consultant synthétique spécialisé dans le pilotage de projets SI, "
            "la coordination métier et la qualité de delivery."
        ),
        "formations": [
            {
                "date": "2018",
                "degree": "Master Management des systèmes d’information",
                "school": "École synthétique",
            }
        ],
        "skills": [
            {
                "category": "Gestion de projet",
                "items": ["Agile Scrum", "Kanban", "Planning", "Reporting", "Risques", "Comités", "Budget"],
            },
            {
                "category": "Fonctionnel",
                "items": ["Cadrage besoin", "Ateliers métier", "User stories", "Backlog", "Recette UAT", "Conduite du changement"],
            },
            {
                "category": "Outils",
                "items": ["Jira", "Confluence", "Miro", "ServiceNow", "Power BI", "Excel avancé"],
            },
            {
                "category": "Technique",
                "items": ["SQL", "API REST", "Data mapping", "Intégration SI", "RGPD", "Tests automatisés"],
            },
            {
                "category": "Secteurs",
                "items": ["Assurance", "Banque", "Retail", "Services", "Relation client"],
            },
            {
                "category": "Qualité",
                "items": ["Stratégie de test", "Plan de recette", "Anomalies", "PV de validation", "Indicateurs qualité"],
            },
            {
                "category": "Communication",
                "items": ["Support comité", "Synthèse exécutive", "Formation utilisateurs", "Documentation projet"],
            },
        ],
        "experiences": [
            _experience(1, 10, long=True),
            _experience(2, 9, long=True),
            _experience(3, 8, long=True),
            _experience(4, 5),
            _experience(5, 4),
            _experience(6, 3),
            _experience(7, 3),
        ],
    }


def test_oussama_like_synthetic_layout_smoke_passes_qa_without_artificial_pages(tmp_path: Path):
    data = _oussama_like_synthetic_cv()
    layout_options = build_layout_packing_options(data)

    assert layout_options["force_experiences_new_page"] is False
    assert layout_options["force_page_break_before_experience_indexes"] == []

    pdf_path = render_pdf(data, tmp_path, layout_options=layout_options)
    report = run_qa(pdf_path, structured_data=data)

    assert report["passed"] is True
    assert report["layout_issues"] == []
    assert 3 <= report["pages"] <= 5

    doc = fitz.open(str(pdf_path))
    sparse_non_final_pages = []
    for metric in collect_page_layout_metrics(doc):
        is_non_final = 1 < int(metric["page"]) < doc.page_count
        is_unacceptably_sparse = float(metric["used_ratio"]) < 0.40 and int(metric["char_count"]) <= 900
        if is_non_final and is_unacceptably_sparse:
            sparse_non_final_pages.append(
                {
                    "page": metric["page"],
                    "used_ratio": round(float(metric["used_ratio"]), 3),
                    "char_count": metric["char_count"],
                }
            )

    assert sparse_non_final_pages == []
