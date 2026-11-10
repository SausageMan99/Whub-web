"""Lot 3 (2026-11) : la colonne « Formation & Diplômes » ne coupe plus rien,
et la QA compare tout le JSON au PDF, section par section. Données anonymisées."""
import json
import subprocess
import sys
from pathlib import Path

import fitz

from src.content_log import CONTENT_WARNINGS_KEY
from src.qa import QAError, collect_json_pdf_coverage, run_qa

RENDERER = Path(__file__).resolve().parents[1] / "renderer" / "whub_cv_renderer.py"


def _render(data, tmp_path: Path, name="output.pdf") -> Path:
    input_path = tmp_path / f"{name}.json"
    output_path = tmp_path / name
    input_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run([sys.executable, str(RENDERER), str(input_path), str(output_path)],
                            text=True, capture_output=True, timeout=180)
    assert result.returncode == 0, result.stderr or result.stdout
    return output_path


def _cv(n_formations=2, n_certs=3, n_langs=2):
    return {
        "name": "LINO",
        "title": "Architecte cloud",
        "formations": [
            {"date": f"20{10 + i}", "degree": f"Diplôme d'ingénieur spécialité {i}", "school": f"École numéro {i}, Ville"}
            for i in range(n_formations)
        ],
        "certifications": [f"Certification Cloud Expert niveau {i} (Éditeur, 20{10 + i})" for i in range(n_certs)],
        "languages": [{"name": name, "level": "courant"} for name in ["Anglais", "Espagnol", "Allemand", "Italien"][:n_langs]],
        "skills": [{"category": "Cloud", "items": ["Azure", "AWS", "Terraform"]}],
        "experiences": [{
            "date": "2020 – 2024", "role": "Architecte", "company_highlight": "Client A",
            "sections": [{"heading": "Missions clés", "content": [f"Mission {j} de conception et de pilotage" for j in range(12)]}],
        }],
    }


def _text(pdf: Path) -> str:
    doc = fitz.open(str(pdf))
    return " ".join(" ".join(page.get_text().split()) for page in doc)


def _lowest_text(pdf: Path) -> float:
    doc = fitz.open(str(pdf))
    return max(b[3] for page in doc for b in page.get_text("blocks") if b[4].strip())


def test_short_sidebar_is_unchanged(tmp_path):
    pdf = _render(_cv(), tmp_path)
    doc = fitz.open(str(pdf))
    first = " ".join(doc[0].get_text().split())

    assert "Certification Cloud Expert niveau 2" in first
    assert "Anglais — courant" in first
    assert "C E R T I F I C A T I O N S" not in _text(pdf)  # pas de section de suite


def test_long_sidebar_continues_after_the_experiences_without_cutting(tmp_path):
    data = _cv(n_formations=4, n_certs=22, n_langs=4)
    pdf = _render(data, tmp_path)
    text = _text(pdf)

    for cert in data["certifications"]:
        assert cert in text
    for lang in data["languages"]:
        assert f"{lang['name']} — courant" in text
    assert "C E R T I F I C A T I O N S" in text
    first = " ".join(fitz.open(str(pdf))[0].get_text().split())
    assert "Allemand — courant" in first  # les langues restent dans la colonne
    assert _lowest_text(pdf) <= fitz.open(str(pdf))[0].rect.height - 30


def test_many_formations_continue_full_width(tmp_path):
    data = _cv(n_formations=14, n_certs=0, n_langs=1)
    pdf = _render(data, tmp_path)
    text = _text(pdf)

    for f in data["formations"]:
        assert f["degree"] in text and f["school"] in text
    assert "F O R M A T I O N & D I P L Ô M E S" in text.replace("  ", " ") or "Formation" in text
    assert _lowest_text(pdf) <= fitz.open(str(pdf))[0].rect.height - 30


def test_qa_coverage_lists_missing_items_per_section(tmp_path):
    data = _cv()
    pdf = _render(data, tmp_path)
    data_with_ghosts = json.loads(json.dumps(data))
    data_with_ghosts["certifications"].append("Certification jamais imprimée")
    data_with_ghosts["languages"].append({"name": "Klingon", "level": "natif"})

    coverage = collect_json_pdf_coverage(fitz.open(str(pdf)), data_with_ghosts)

    assert coverage["sections"]["certifications"]["missing"] == ["Certification jamais imprimée"]
    assert coverage["sections"]["languages"]["missing"] == ["Klingon", "natif"]
    assert coverage["sections"]["experiences"]["missing"] == []
    assert coverage["missing_count"] == 3


def test_run_qa_reports_coverage_and_content_warnings_as_warnings(tmp_path):
    data = _cv()
    pdf = _render(data, tmp_path)
    structured = json.loads(json.dumps(data))
    structured["certifications"].append("Certification jamais imprimée")
    structured[CONTENT_WARNINGS_KEY] = [{"code": "placeholder_removed", "message": "1 valeur retirée"}]

    try:
        report = run_qa(pdf, structured_data=structured)
    except QAError as error:
        report = error.report

    codes = [w["code"] for w in report["content_warnings"]]
    assert "placeholder_removed" in codes
    assert "content_missing_from_pdf" in codes
    assert report["content_coverage"]["sections"]["certifications"]["missing"] == ["Certification jamais imprimée"]
