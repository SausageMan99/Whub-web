from pathlib import Path

import fitz
import pytest

from src import extraction
from src.quality_report import classify_source_profile, should_require_human_review
from src.text_readability import READABILITY_OCR_THRESHOLD, text_readability

READABLE = "\n".join([
    "Développeur Java senior avec huit ans d'expérience sur des projets bancaires.",
    "Conception de microservices Spring Boot et mise en place de pipelines CI/CD.",
    "Accompagnement des équipes de développement sur les bonnes pratiques de test.",
] * 4)
# Shape of a PDF whose embedded fonts map glyphs to private codes (Benjamin).
GIBBERISH = "Z<-.* A).*(&@ ).*() @)+ [\\,-X)+ +,XX<(* )* @)+ ?[*-)(+ ]^_Z ` abcdeYf &g)A ,. (h@) " * 12


def _pdf(tmp_path: Path) -> Path:
    path = tmp_path / "source.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    return path


def test_readability_separates_text_from_font_map_gibberish():
    assert text_readability(READABLE) > 0.85
    assert text_readability(GIBBERISH) < 0.1
    assert text_readability("") == 0.0


def test_gibberish_text_layer_is_replaced_by_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(extraction, "_page_text_visual_order", lambda page, textpage=None: GIBBERISH)
    monkeypatch.setattr(extraction, "_ocr_pdf_text", lambda doc: READABLE)

    assert extraction.extract_pdf_text(_pdf(tmp_path)) == READABLE


def test_readable_text_layer_skips_ocr(tmp_path, monkeypatch):
    def fail_ocr(doc):
        raise AssertionError("OCR must not run on a readable text layer")

    monkeypatch.setattr(extraction, "_page_text_visual_order", lambda page, textpage=None: READABLE)
    monkeypatch.setattr(extraction, "_ocr_pdf_text", fail_ocr)

    assert extraction.extract_pdf_text(_pdf(tmp_path)) == READABLE


def test_ocr_failure_keeps_native_text_and_routes_to_human_review(tmp_path, monkeypatch):
    def broken_ocr(doc):
        raise RuntimeError("tesseract missing")

    monkeypatch.setattr(extraction, "_page_text_visual_order", lambda page, textpage=None: GIBBERISH)
    monkeypatch.setattr(extraction, "_ocr_pdf_text", broken_ocr)

    text = extraction.extract_pdf_text(_pdf(tmp_path))
    profile = classify_source_profile(text)

    assert profile["readability"] < READABILITY_OCR_THRESHOLD
    assert should_require_human_review(profile) is True


def test_readable_profile_does_not_require_human_review():
    assert should_require_human_review(classify_source_profile(READABLE)) is False


BENJAMIN_PDF = Path(__file__).resolve().parents[3] / "cv_test_bank" / "Benjamin_control_chars" / "input.pdf"


@pytest.mark.skipif(not BENJAMIN_PDF.exists(), reason="test-bank PDF not present (gitignored)")
def test_benjamin_fixture_is_rescued_by_real_ocr():
    text = extraction.extract_pdf_text(BENJAMIN_PDF)

    assert text_readability(text) > 0.7
    assert "Lead Support IT" in text


def test_typographic_ligatures_are_expanded():
    assert extraction._clean_extracted_text("mise en place du ﬁchier Docker, ﬂux, eﬀort") == "mise en place du fichier Docker, flux, effort"


def test_symbol_font_bullets_become_regular_bullets():
    # Yannick: Wingdings bullets are extracted as private-use glyphs, alone on
    # their line, the bullet text following on the next line.
    raw = "Missions\n\nRefonte d'un POC sous .NET Core\n Analyse de l'existant\n\n\nDéveloppement"

    assert extraction._clean_extracted_text(raw) == (
        "Missions\n• Refonte d'un POC sous .NET Core\n• Analyse de l'existant\n• Développement"
    )


def test_word_sub_bullets_alone_on_their_line_become_bullets():
    raw = "Principes architecturaux :\no\nMicroservices\no\nArchitecture monolithique\nDesign patterns"

    assert extraction._clean_extracted_text(raw) == (
        "Principes architecturaux :\n• Microservices\n• Architecture monolithique\nDesign patterns"
    )
