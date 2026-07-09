from __future__ import annotations

import importlib.util
from pathlib import Path

import fitz

from src.visual_skills_extraction import extract_visual_skills


ROOT = Path(__file__).resolve().parents[3]
OMAR_PDF = ROOT / "cv_test_bank" / "Omar_skills_source_categories" / "input.pdf"
RENDERER_PATH = Path(__file__).resolve().parents[1] / "renderer" / "whub_cv_renderer.py"
spec = importlib.util.spec_from_file_location("whub_cv_renderer_e2e", RENDERER_PATH)
assert spec and spec.loader
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
renderer.prep_assets()
renderer.register_fonts(renderer.ensure_poppins())


def test_omar_source_skills_render_as_structured_categories_without_autres(tmp_path):
    visual = extract_visual_skills(OMAR_PDF)
    output = tmp_path / "omar.pdf"
    data = {
        "name": "Omar",
        "title": "Ingénieur Consultant Expert .NET",
        "formations": [{"date": "2004-2007", "degree": "Ingénieur", "school": "E.M.I"}],
        "skills": visual.skills,
        "experiences": [
            {
                "date": "Depuis Décembre 2015",
                "role": "Consultant Expert .NET — Client",
                "sections": [
                    {
                        "heading": "Contributions",
                        "content": [
                            "Architecture et développement de briques techniques transverses.",
                            "Conception d’outils de génération de code.",
                        ],
                    }
                ],
            }
        ],
    }

    renderer.Renderer(str(output)).render(data)
    text = "\n".join(str(page.get_text("text")) for page in fitz.open(str(output)))

    assert "C O M P É T E N C E S" in text
    assert "Front-end" in text
    assert "Ops" in text
    assert "Réseau & Sécurité" in text
    assert "Qualité & Analyse" in text
    assert "Autres" not in text
    assert "Git · GitHub" in text or "Git GitHub" in text


def test_experience_heading_moves_with_first_experience_when_skills_leave_too_little_room(tmp_path):
    output = tmp_path / "sparse.pdf"
    long_skills = [
        {"category": f"Catégorie {idx}", "items": [f"Compétence {idx}-{item}" for item in range(14)]}
        for idx in range(12)
    ]
    data = {
        "name": "Omar",
        "title": "Ingénieur Consultant Expert .NET",
        "formations": [],
        "skills": long_skills,
        "experiences": [
            {
                "date": "Depuis Décembre 2015",
                "role": "Consultant Expert .NET — Client",
                "sections": [
                    {
                        "heading": "Contributions",
                        "content": [
                            "Architecture et développement de briques techniques transverses avec gouvernance technique et accompagnement des équipes.",
                            "Conception d’outils de génération de code et mise en place d’un socle industriel durable.",
                            "Refactoring, tests, analyse et amélioration continue des plateformes.",
                        ],
                    }
                ],
            }
        ],
    }

    renderer.Renderer(str(output)).render(data)
    doc = fitz.open(str(output))
    page1_text = str(doc[0].get_text("text"))

    assert "E X P É R I E N C E S" not in page1_text
