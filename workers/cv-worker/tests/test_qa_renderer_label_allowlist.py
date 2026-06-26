import tempfile
from pathlib import Path

import fitz
import pytest

from src.qa import find_pdf_source_fidelity_issues, run_qa


def _make_pdf(text: str | None = None) -> tuple[Path, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    if text:
        page.insert_text((72, 120), text, fontsize=12)
    fake_logo = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1051, 398), 0)
    fake_wm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1192, 1192), 0)
    page.insert_image(fitz.Rect(400, 700, 500, 800), pixmap=fake_logo)
    page.insert_image(fitz.Rect(400, 700, 500, 800), pixmap=fake_wm)
    doc.save(path)
    doc.close()
    return path, tmp


class TestPdfFactAbsentFromSourceRendererLabelAllowlist:
    def test_database_label_in_pdf_not_flagged_when_source_has_database(self):
        pdf_text = "Database\nPostgreSQL"
        source_text = "Database\nPostgreSQL"
        assert find_pdf_source_fidelity_issues(pdf_text, source_text=source_text) == []

    def test_bases_de_donnees_label_in_pdf_not_flagged_when_source_has_database(self):
        pdf_text = "Bases de données\nPostgreSQL"
        source_text = "Database\nPostgreSQL"
        assert find_pdf_source_fidelity_issues(pdf_text, source_text=source_text) == []

    def test_bases_de_donnees_label_not_flagged_for_normal_cv_with_database_section(self):
        pdf_text = "Jean Dupont\nArchitecte Cloud\nBases de données\nPostgreSQL, MongoDB"
        source_text = "Jean Dupont\nArchitecte Cloud\nDatabase\nPostgreSQL, MongoDB"
        assert find_pdf_source_fidelity_issues(pdf_text, source_text=source_text) == []

    def test_competences_techniques_label_not_flagged_when_source_has_competences(self):
        pdf_text = "Compétences techniques\nPython, AWS"
        source_text = "Compétences\nPython, AWS"
        assert find_pdf_source_fidelity_issues(pdf_text, source_text=source_text) == []

    def test_skills_label_not_flagged_when_source_has_skills(self):
        pdf_text = "Skills\nPython, Docker"
        source_text = "Skills\nPython, Docker"
        assert find_pdf_source_fidelity_issues(pdf_text, source_text=source_text) == []

    def test_real_fact_still_flagged_when_absent_from_source(self):
        pdf_text = "Jean Dupont\nChef de projet\nMutuelle GSMC"
        source_text = "Jean Dupont\nChef de projet\nGROUPE KLESIA"
        issues = find_pdf_source_fidelity_issues(pdf_text, source_text=source_text)
        assert any(issue["code"] == "pdf_fact_absent_from_source" for issue in issues)
        assert any("Mutuelle GSMC" in issue.get("fact", "") for issue in issues)
