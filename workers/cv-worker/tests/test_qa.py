import tempfile
from pathlib import Path

import fitz
import pytest

from src.qa import run_qa, QAError, find_text_overflow, find_pdf_source_fidelity_issues
from src.structuring import StructuringError, validate_source_fidelity, extract_experience_location_facts


class TestRunQA:
    def _make_pdf(self, text: str | None = None, draw=None) -> tuple[Path, tempfile.TemporaryDirectory]:
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "sample.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        if text:
            page.insert_text((72, 120), text, fontsize=12)
        if draw:
            draw(doc, page)
        # Insert fake logo/watermark images so has_logo/has_watermark pass
        logo_pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1051, 398), 0)
        wm_pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1192, 1192), 0)
        page.insert_image(fitz.Rect(400, 700, 500, 800), pixmap=logo_pix)
        page.insert_image(fitz.Rect(400, 700, 500, 800), pixmap=wm_pix)
        doc.save(path)
        doc.close()
        return path, tmp

    def test_passes_on_clean_pdf(self):
        path, tmp = self._make_pdf("Jean Dupont\nArchitecte Cloud\nPython AWS")
        report = run_qa(path)
        assert report["passed"] is True
        assert report["contact_hits"] == []
        assert report["bad_glyphs"] is False
        tmp.cleanup()

    def test_detects_email_in_text(self):
        path, tmp = self._make_pdf("Contact: jean.dupont@example.com")
        with pytest.raises(QAError) as exc_info:
            run_qa(path)
        assert "email" in exc_info.value.report["contact_hits"]
        tmp.cleanup()

    def test_detects_linkedin_in_text(self):
        path, tmp = self._make_pdf("Profil linkedin.com/in/jean")
        with pytest.raises(QAError) as exc_info:
            run_qa(path)
        assert "linkedin" in exc_info.value.report["contact_hits"]
        tmp.cleanup()

    def test_detects_phone_in_text(self):
        path, tmp = self._make_pdf("Tél: 0612345678")
        with pytest.raises(QAError) as exc_info:
            run_qa(path)
        assert "phone_fr" in exc_info.value.report["contact_hits"]
        tmp.cleanup()

    def test_detects_url_in_text(self):
        path, tmp = self._make_pdf("Site: https://github.com/jean")
        with pytest.raises(QAError) as exc_info:
            run_qa(path)
        assert "url" in exc_info.value.report["contact_hits"]
        tmp.cleanup()

    def test_detects_forbidden_name(self):
        path, tmp = self._make_pdf("Jean Dupont est un consultant.")
        with pytest.raises(QAError) as exc_info:
            run_qa(path, forbidden_names=["Dupont"])
        assert any("forbidden_name:Dupont" in hit for hit in exc_info.value.report["contact_hits"])
        tmp.cleanup()

    def test_detects_bad_glyphs(self):
        path, tmp = self._make_pdf("Texte avec NUL\x00caractere")
        with pytest.raises(QAError) as exc_info:
            run_qa(path)
        assert exc_info.value.report["bad_glyphs"] is True
        tmp.cleanup()

    def test_reports_multiple_contact_hits(self):
        path, tmp = self._make_pdf("Email: a@b.com\nLinkedIn: linkedin/in/jean\nTel: 0612345678")
        with pytest.raises(QAError) as exc_info:
            run_qa(path)
        hits = exc_info.value.report["contact_hits"]
        assert "email" in hits
        assert "linkedin" in hits
        assert "phone_fr" in hits
        tmp.cleanup()

    def test_detects_numbered_placeholder_bullets(self):
        path, tmp = self._make_pdf("Analyse des besoins assurance 1\nAnalyse des besoins assurance 2\nAnalyse des besoins assurance 3")
        with pytest.raises(QAError) as exc_info:
            run_qa(path)
        assert any(issue["code"] == "numbered_placeholder_repetition" for issue in exc_info.value.report["content_integrity_issues"])
        tmp.cleanup()

    def test_pdf_gate_rejects_json_experience_missing_from_rendered_pdf(self):
        path, tmp = self._make_pdf("Zahia\nChef de projet\nGROUPE KLESIA")
        structured = {
            "name": "ZAHIA",
            "title": "Chef de projet",
            "formations": [],
            "skills": [],
            "experiences": [{
                "date": "Juin 2023 – à ce jour",
                "role": "Chef de projet | GROUPE KLESIA | Protection sociale",
                "company_highlight": "GROUPE KLESIA",
                "sections": [{"heading": "Missions clés", "content": ["Pilotage recette"]}],
            }],
        }

        with pytest.raises(QAError) as exc_info:
            run_qa(path, source_text="Zahia\nJuin 2023 – à ce jour\nChef de projet | GROUPE KLESIA | Protection sociale\nPilotage recette", structured_data=structured)
        assert any(issue["code"] == "json_fact_missing_from_pdf" for issue in exc_info.value.report["content_integrity_issues"])
        tmp.cleanup()

    def test_pdf_gate_rejects_pdf_company_absent_from_source(self):
        path, tmp = self._make_pdf("Zahia\nChef de projet\nMutuelle GSMC")
        with pytest.raises(QAError) as exc_info:
            run_qa(path, source_text="Zahia\nChef de projet\nGROUPE KLESIA")
        assert any(issue["code"] == "pdf_fact_absent_from_source" for issue in exc_info.value.report["content_integrity_issues"])
        tmp.cleanup()

    def test_pdf_source_fidelity_accepts_line_break_and_punctuation_normalization(self):
        pdf_text = "Langages : Python, Angular, JavaScript, MySQL, Jenkins. Logiciels : PEGA"
        source_text = "Langages : Python, Angular, JavaScript, MySQL, Jenkins,\nLogiciels : PEGA"

        issues = find_pdf_source_fidelity_issues(pdf_text, source_text=source_text)

        assert issues == []

    def test_pdf_source_fidelity_accepts_comparison_symbol_normalization(self):
        pdf_text = "Objectifs prévisionnels : −30 % sur le délai demande d’achat, commande | ≥ 90 % des demandes dans SAP/SRM"
        source_text = "Objectifs prévisionnels : −30 % sur le délai demande d’achat, commande | ≥ 90 % des demandes dans SAP/SRM"

        issues = find_pdf_source_fidelity_issues(pdf_text, source_text=source_text)

        assert issues == []

    def test_pdf_source_fidelity_accepts_ocr_split_inside_word(self):
        pdf_text = "≥ 90 % des demandes dans SAP/SRM"
        source_text = "90 % des de mandes dans SAP/SRM"

        issues = find_pdf_source_fidelity_issues(pdf_text, source_text=source_text)

        assert issues == []

    def test_extracts_and_requires_experience_locations_without_personal_city(self):
        source_text = "Zahia Aris\nzaris@example.com\nJouy-Le-Moutier\nGROUPE KLESIA 📌 Montreuil (93)\n📆 Juin 2023 – A ce jour\nCHEF DE PROJET"
        assert extract_experience_location_facts(source_text) == ["Montreuil (93)"]

        data = {
            "name": "ZAHIA",
            "title": "Chef de projet",
            "formations": [],
            "skills": [],
            "experiences": [{"date": "Juin 2023 – A ce jour", "role": "GROUPE KLESIA — Chef de projet", "company_highlight": "GROUPE KLESIA", "sections": []}],
        }
        with pytest.raises(StructuringError) as exc_info:
            validate_source_fidelity(source_text, data)
        assert "experience_location_missing_from_json" in str(exc_info.value)

        data["experiences"][0]["role"] = "GROUPE KLESIA — Montreuil (93) — Chef de projet"
        validate_source_fidelity(source_text, data)

    def test_pdf_source_fidelity_rejects_missing_experience_location(self):
        source_text = "GROUPE KLESIA 📌 Montreuil (93)\n📆 Juin 2023 – A ce jour"
        pdf_text = "GROUPE KLESIA\nJuin 2023 – A ce jour\nChef de projet"

        issues = find_pdf_source_fidelity_issues(pdf_text, source_text=source_text)

        assert any(issue["code"] == "source_experience_location_missing_from_pdf" for issue in issues)


    def test_pdf_source_coverage_rejects_missing_business_realizations_section(self):
        source_text = """
THOREZ Nicolas
06 66 44 13 14
Exemples de réalisations professionnelles
:
✓Gestion d'un SI d'une usine pharmaceutique (+500 employés)
✓Conception, développement et mise en place d’une application de suivi de prestations (85 000 logements) via app mobile & QR codes installés dans les parties communes (#10 000 QR codes suivis) [Point Of Control Vilogia]
Compétences et outils :
✓Management d'équipe
"""
        pdf_text = "NICOLAS\nCompétences et outils\nManagement d'équipe"

        issues = find_pdf_source_fidelity_issues(pdf_text, source_text=source_text)

        assert any(issue["code"] == "source_coverage_missing_section" for issue in issues)
        assert any("Exemples de réalisations professionnelles" in issue.get("section", "") for issue in issues)

    def test_forbidden_name_does_not_match_inside_city_name(self):
        path, tmp = self._make_pdf("ESAM School, Paris")

        report = run_qa(path, forbidden_names=["Aris"])

        assert report["passed"] is True
        assert report["contact_hits"] == []
        tmp.cleanup()
