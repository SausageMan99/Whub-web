"""Lot 5 (2026-11) : typographie réparée et en-têtes/pieds du CV source
retirés à l'extraction. Données anonymisées."""
from pathlib import Path

import fitz
import pytest

from src.extraction import extract_pdf_text, find_page_furniture
from src.text_repair import (
    find_broken_ligatures,
    repair_broken_ligatures,
    repair_detached_capitals,
    repair_missing_space_after_punctuation,
    text_vocabulary,
)


@pytest.mark.parametrize("broken, fixed", [
    ("les di érents SI", "les différents SI"),
    ("pour e ectuer la recette", "pour effectuer la recette"),
    ("a n de garantir", "afin de garantir"),
    ("rédaction de l'o re", "rédaction de l'offre"),
    ("con guration des pro ls", "configuration des profils"),
    ("spéci cations fonctionnelles", "spécifications fonctionnelles"),
    ("export du chier client", "export du fichier client"),
    ("tâche di cile", "tâche difficile"),
    ("work ow de validation", "workflow de validation"),
])
def test_lost_ligatures_are_restored(broken, fixed):
    assert repair_broken_ligatures(broken)[0] == fixed


@pytest.mark.parametrize("text", [
    "risk management in banking",
    "Tests E2E et de non-régression",
    "chef de projet et agents conversationnels",
    "Développement et exécution des tests, délais tenus",
    "scalabilité et exigences de sécurité",
    "Lead dev et legacy",
])
def test_real_words_are_left_alone(text):
    assert repair_broken_ligatures(text) == (text, 0)
    assert find_broken_ligatures(text) == []


def test_detached_capital_is_joined_only_when_the_rest_is_not_a_word():
    text = "L ead Product Designer. D éveloppement front. Gestion de parc G projets et des projets. I help teams."
    fixed, count = repair_detached_capitals(text, text_vocabulary([text]))

    assert "Lead Product Designer" in fixed
    assert "Développement front" in fixed
    assert "G projets" in fixed  # « projets » est un mot du document
    assert "I help" in fixed
    assert count == 2


@pytest.mark.parametrize("text, expected", [
    ("besoins métiers.Cette approche", "besoins métiers. Cette approche"),
    ("patients et praticiens.Création du design system", "patients et praticiens. Création du design system"),
    ("Office.Interop et Xamarin.Android", "Office.Interop et Xamarin.Android"),
    ("ASP.NET, Vue.js, Node.Js", "ASP.NET, Vue.js, Node.Js"),
])
def test_missing_space_after_full_stop(text, expected):
    assert repair_missing_space_after_punctuation(text)[0] == expected


def _pdf_with_running_header(path: Path, pages: int = 3) -> Path:
    doc = fitz.open()
    for number in range(1, pages + 1):
        page = doc.new_page(width=595, height=842)
        page.insert_text((70, 60), "D O S S I E R  D E  C O M P E T E N C E S", fontsize=9)
        body = "\n".join(f"Mission {number}.{line} : pilotage des recettes et des livraisons applicatives" for line in range(1, 12))
        page.insert_text((70, 200), body, fontsize=10)
        page.insert_text((70, 790), f"Ines · Analyste QA      Page {number} / {pages}", fontsize=8)
    doc.save(path)
    doc.close()
    return path


def test_running_headers_and_footers_are_not_extracted(tmp_path):
    pdf = _pdf_with_running_header(tmp_path / "cv.pdf")

    text = extract_pdf_text(pdf)

    assert "Page 2 / 3" not in text and "Page 1 / 3" not in text
    assert text.count("D O S S I E R") == 1  # en-tête de la page 1 gardé
    assert "Mission 3.11" in text


def test_find_page_furniture_lists_repeated_band_text(tmp_path):
    pdf = _pdf_with_running_header(tmp_path / "cv.pdf")

    skip, texts = find_page_furniture(fitz.open(pdf))

    assert set(skip) == {0, 1, 2}
    assert any("Analyste QA" in t for t in texts)


def test_single_page_cv_keeps_its_header(tmp_path):
    pdf = _pdf_with_running_header(tmp_path / "cv.pdf", pages=1)

    text = extract_pdf_text(pdf)

    assert "D O S S I E R" in text
