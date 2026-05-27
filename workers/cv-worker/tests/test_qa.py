import tempfile
from pathlib import Path

import fitz
import pytest

from src.qa import run_qa, QAError, find_text_overflow


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
