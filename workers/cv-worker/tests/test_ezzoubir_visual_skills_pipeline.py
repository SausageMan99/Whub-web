from pathlib import Path

from src.visual_skills_extraction import apply_visual_skills_override, extract_visual_skills

ROOT = Path(__file__).resolve().parents[3]
EZZOUBIR_PDF = ROOT / "cv_test_bank" / "Ezzoubir_skills_section_preservation" / "input.pdf"


def test_ezzoubir_visual_skills_override_removes_llm_pollution():
    llm_structured = {
        "skills": [
            {
                "category": "Backend",
                "items": [
                    "C#",
                    "Java",
                    "6 CV créé sur IMSBATCH PCB MSDB BATCH/TP IBM TOOLS COMPUWARE TOOLS",
                ],
            },
            {"category": "Autres", "items": ["Compétences fonctionnelles Le lexique de la banque"]},
        ]
    }

    visual = extract_visual_skills(EZZOUBIR_PDF)
    result = apply_visual_skills_override(llm_structured, visual, min_confidence=0.75)
    flat = "\n".join(item for skill in result["skills"] for item in skill["items"])

    assert result["skills"] != llm_structured["skills"]
    assert "Backend" not in [skill["category"] for skill in result["skills"]]
    assert "Autres" not in [skill["category"] for skill in result["skills"]]
    assert "CV créé sur" not in flat
    assert "6 CV créé sur" not in flat
    assert "Le lexique de la banque" in flat
    assert "COBOL" in flat
