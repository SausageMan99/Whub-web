import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest

from src.extraction import download_source, extract_pdf_text, ExtractionError


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
