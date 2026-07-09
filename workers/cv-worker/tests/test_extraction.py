import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest

from src.extraction import (
    download_source,
    extract_pdf_text,
    ExtractionError,
    _page_text_visual_order,
    _normalize_pdf_text_chars,
    _strip_pdf_footer_lines,
)


class TestDownloadSource:
    def test_download_source_writes_pdf_and_returns_path(self, tmp_path: Path):
        job = {"source_file_path": "uploads/cv_123.pdf"}
        fake_bytes = b"%PDF-1.4 fake pdf content"

        mock_storage = MagicMock()
        mock_storage.storage.from_.return_value.download.return_value = fake_bytes

        with patch("src.extraction.client", mock_storage):
            with patch("src.extraction.settings.cv_sources_bucket", "cv-sources"):
                result = download_source(job, tmp_path)

        assert result == tmp_path / "source.pdf"
        assert result.read_bytes() == fake_bytes
        mock_storage.storage.from_.assert_called_once_with("cv-sources")
        mock_storage.storage.from_.return_value.download.assert_called_once_with("uploads/cv_123.pdf")


class TestExtractPdfText:
    def test_page_text_visual_order_sorts_blocks_by_position(self):
        class FakePage:
            def get_text(self, kind):
                assert kind == "blocks"
                return [
                    (27.2, 251.1, 528.2, 307.1, "Mission CEA", 0, 0),
                    (8.5, 118.0, 587.3, 133.6, "Ingénieur Système et Réseau, Nat System", 0, 0),
                    (27.2, 138.9, 559.3, 224.9, "Mission Nat System", 0, 0),
                    (8.5, 230.2, 587.3, 245.8, "Alternance - Ingénieur Réseau, CEA", 0, 0),
                ]

        result = _page_text_visual_order(FakePage())

        assert result.splitlines() == [
            "Ingénieur Système et Réseau, Nat System",
            "Mission Nat System",
            "Alternance - Ingénieur Réseau, CEA",
            "Mission CEA",
        ]

    def test_page_text_visual_order_keeps_two_column_main_content_contiguous(self):
        class Rect:
            width = 600

        class FakePage:
            rect = Rect()

            def get_text(self, kind):
                assert kind == "blocks"
                return [
                    (210, 100, 560, 110, "EXPÉRIENCES PROFESSIONNELLES", 0, 0),
                    (210, 120, 560, 130, "Technicien Systèmes & Réseaux", 0, 0),
                    (32, 125, 185, 135, "COMPÉTENCES", 0, 0),
                    (210, 140, 560, 150, "Mission expérience 1", 0, 0),
                    (32, 145, 185, 155, "Skill sidebar 1", 0, 0),
                    (210, 160, 560, 170, "Mission expérience 2", 0, 0),
                    (32, 165, 185, 175, "Skill sidebar 2", 0, 0),
                    (210, 180, 560, 190, "FORMATION", 0, 0),
                    (32, 185, 185, 195, "CERTIFICATIONS", 0, 0),
                    (210, 200, 560, 210, "Projet BTS SIO", 0, 0),
                ]

        result = _page_text_visual_order(FakePage())
        lines = result.splitlines()

        assert lines.index("Mission expérience 2") < lines.index("COMPÉTENCES")
        assert lines.index("Projet BTS SIO") < lines.index("Skill sidebar 1")

    def test_normalize_pdf_text_chars_replaces_superscripts(self):
        assert _normalize_pdf_text_chars("1ʳᵉ & 2ᵉ année") == "1re & 2e année"

    def test_strip_pdf_footer_lines_removes_hellowork_footer_lines(self):
        text = "COBOL\n3 / 6\nCV créé sur\n4 / 6 CV créé sur\nJava"

        result = _strip_pdf_footer_lines(text)

        assert result == "COBOL\nJava"

    def test_extract_pdf_text_returns_text(self, tmp_path: Path):
        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        long_text = "Ligne de texte du CV.\n" * 50  # > 400 chars
        page.insert_text((72, 72), long_text, fontsize=12)
        doc.save(pdf_path)
        doc.close()

        result = extract_pdf_text(pdf_path)
        assert len(result.strip()) >= 400
        assert "Ligne de texte du CV." in result

    def test_extract_pdf_text_raises_when_text_too_short(self, tmp_path: Path):
        pdf_path = tmp_path / "short.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), "Trop court", fontsize=12)
        doc.save(pdf_path)
        doc.close()

        with pytest.raises(ExtractionError, match="trop court"):
            extract_pdf_text(pdf_path)

    def test_extract_pdf_text_raises_on_empty_pdf(self, tmp_path: Path):
        pdf_path = tmp_path / "empty.pdf"
        doc = fitz.open()
        doc.new_page(width=595, height=842)
        doc.save(pdf_path)
        doc.close()

        with pytest.raises(ExtractionError, match="trop court"):
            extract_pdf_text(pdf_path)
