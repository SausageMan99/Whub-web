"""Tests for the post-process that rescues spoken languages and certifications from
`skills[Langues]` / `skills[Certifications]` into the top-level `languages` and
`certifications` fields, and for the new "Formation & Diplômes" sidebar rendering.

These tests lock the behaviour that the user expects on the right-side column of
the W hub CV PDF: a single "Formation & Diplômes" section that groups academic
diplomas, candidate certifications and spoken languages — and never mixes spoken
languages with programming languages in the same UI block.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from src.config import DEFAULT_WHUB_ASSETS_DIR, DEFAULT_WHUB_FONTS_DIR, DEFAULT_WHUB_RENDERER_PATH
from src.structuring import (
    _extract_languages_from_skill_item,
    _is_certification_like_text,
    _looks_like_spoken_language_token,
    _postprocess_skills_into_languages_and_certifications,
)


# ---------------------------------------------------------------------------
# Token detection
# ---------------------------------------------------------------------------

class TestSpokenLanguageTokenDetection:
    def test_recognises_french_arabic_english(self):
        assert _looks_like_spoken_language_token("Arabe")
        assert _looks_like_spoken_language_token("Français")
        assert _looks_like_spoken_language_token("Anglais")

    def test_recognises_lowercase_and_accents(self):
        assert _looks_like_spoken_language_token("français")
        assert _looks_like_spoken_language_token("allemand")

    def test_rejects_programming_languages(self):
        # These are programming languages and must NEVER be detected as spoken languages.
        for token in ("Java", "Python", "JavaScript", "C#", "PHP", "Ruby", "Go", "Rust", "TypeScript", "SQL"):
            assert not _looks_like_spoken_language_token(token), f"false positive on {token}"

    def test_rejects_short_tokens(self):
        assert not _looks_like_spoken_language_token("C")
        assert not _looks_like_spoken_language_token("R")
        assert not _looks_like_spoken_language_token("ab")


# ---------------------------------------------------------------------------
# Blob extraction
# ---------------------------------------------------------------------------

class TestExtractLanguagesFromSkillItem:
    def test_extracts_languages_with_numeric_levels_from_blob(self):
        # Real-world Imed V51 case: a single skills item blob.
        item = "Arabe 5 Français 4 Anglais 4 Developpement Java8 Java17 Junit UML Spring Core"
        langs, residual = _extract_languages_from_skill_item(item)
        names = [l["name"] for l in langs]
        assert "Arabe" in names
        assert "Français" in names
        assert "Anglais" in names
        # Numeric levels are captured.
        levels = {l["name"]: l["level"] for l in langs}
        assert levels["Arabe"] == "5"
        assert levels["Français"] == "4"
        assert levels["Anglais"] == "4"
        # Residual contains the programming languages / frameworks, not the spoken ones.
        assert "Developpement" in residual
        assert "Java8" in residual
        assert "Spring" in residual
        assert "Arabe" not in residual
        assert "Anglais" not in residual

    def test_returns_empty_when_no_spoken_language_in_item(self):
        item = "Spring Boot, Hibernate, Maven, JUnit 5, Docker, Kubernetes"
        langs, residual = _extract_languages_from_skill_item(item)
        assert langs == []
        assert residual == item

    def test_handles_short_language_only_item(self):
        item = "Anglais — courant"
        # The em-dash + "courant" is not a separate token in our regex; "Anglais" alone is detected.
        langs, _ = _extract_languages_from_skill_item(item)
        assert any(l["name"] == "Anglais" for l in langs)


# ---------------------------------------------------------------------------
# Certification detection
# ---------------------------------------------------------------------------

class TestCertificationLikeText:
    def test_recognises_oracle_certified_associate(self):
        assert _is_certification_like_text("Oracle Certified Associate Java SE 8")

    def test_recognises_aws(self):
        assert _is_certification_like_text("AWS Solutions Architect Associate")

    def test_recognises_scrum(self):
        assert _is_certification_like_text("Professional Scrum Master I")

    def test_rejects_spoken_language_blob(self):
        # Should never catch a spoken language line as a certification.
        assert not _is_certification_like_text("Anglais — courant")

    def test_rejects_plain_tech_skill(self):
        assert not _is_certification_like_text("Spring Boot")


# ---------------------------------------------------------------------------
# End-to-end post-process
# ---------------------------------------------------------------------------

class TestPostprocessSkillsIntoLanguagesAndCertifications:
    def test_recovers_languages_from_skills_langues_category(self):
        # The exact Imed V51 case observed in production.
        data = {
            "name": "IMED",
            "title": "Dev",
            "formations": [],
            "skills": [
                {"category": "Certifications", "items": ["Oracle Certified Associate Java SE 8"]},
                {
                    "category": "Langues",
                    "items": [
                        "Arabe 5 Français 4 Anglais 4 Developpement Java8 Java17 Junit UML Spring Core Spring Batch JBoss RabbitMQ Base de données Oracle PostgreSQL IDE Intellij Netbeans Eclipse Gestion de versions GIT SVN Outils d'intégration continue Jira Code collab Jenkins Nexus"
                    ],
                },
            ],
            "experiences": [],
        }
        out = _postprocess_skills_into_languages_and_certifications(data)
        # Spoken languages moved to top-level.
        names = sorted(l["name"] for l in out.get("languages") or [])
        assert names == ["Anglais", "Arabe", "Français"]
        # Original input is not mutated.
        assert "languages" not in data
        # Certifications moved to top-level.
        assert out.get("certifications") == ["Oracle Certified Associate Java SE 8"]
        # The Certifications category is dropped from skills (top-level owns this data now).
        cats = [s.get("category") for s in out["skills"]]
        assert "Certifications" not in cats
        # The Langues category may be dropped (no residual) OR kept with the programming languages
        # as residual. The contract: NO spoken language name (Arabe, Français, Anglais) leaks into
        # the residual items, and the residual is a single non-empty string.
        if "Langues" in cats:
            langues_items = next(s["items"] for s in out["skills"] if s["category"] == "Langues")
            residual = " ".join(langues_items)
            assert "Arabe" not in residual
            assert "Français" not in residual
            assert "Anglais" not in residual
            assert residual.strip()  # not empty

    def test_residual_is_relocated_to_technical_category(self):
        # If the Langues category mixes real spoken languages with real programming languages,
        # the spoken languages move to top-level `languages` and the programming residual is
        # relocated to a technical category (or merged into an existing one) — it must NEVER
        # stay under "Langues".
        data = {
            "name": "X",
            "title": "Dev",
            "formations": [],
            "skills": [
                {"category": "Backend", "items": ["Python", "Django"]},
                {
                    "category": "Langues",
                    "items": ["Français — courant", "Anglais — technique", "Java 17", "Spring Boot 3"],
                },
            ],
            "experiences": [],
        }
        out = _postprocess_skills_into_languages_and_certifications(data)
        names = sorted(l["name"] for l in out.get("languages") or [])
        assert names == ["Anglais", "Français"]
        # The "Langues" category is gone.
        cats = [s.get("category") for s in out["skills"]]
        assert "Langues" not in cats
        # The Java + Spring residual is merged into the existing "Backend" category.
        backend = next(s for s in out["skills"] if s["category"] == "Backend")
        assert "Java 17" in backend["items"]
        assert "Spring Boot 3" in backend["items"]
        assert "Python" in backend["items"]
        assert "Django" in backend["items"]

    def test_residual_is_renamed_when_no_technical_category(self):
        # When no existing technical category can absorb the residual, the category is renamed
        # from "Langues" to a technical one (never stays as "Langues").
        data = {
            "name": "X",
            "title": "Dev",
            "formations": [],
            "skills": [
                {
                    "category": "Langues",
                    "items": ["Français — courant", "Anglais — technique", "Java 17", "Spring Boot 3"],
                },
            ],
            "experiences": [],
        }
        out = _postprocess_skills_into_languages_and_certifications(data)
        # "Langues" is no longer present in skills.
        cats = [s.get("category") for s in out["skills"]]
        assert "Langues" not in cats
        # The residual sits under a renamed technical category.
        assert any(c in cats for c in ("Stack principale", "Outils & Environnements", "Backend", "Langages"))
        # The Java + Spring items are kept (no other category to merge into).
        tech_cat = next(s for s in out["skills"] if s["category"] != "Langues")
        assert "Java 17" in tech_cat["items"]
        assert "Spring Boot 3" in tech_cat["items"]
        # Spoken languages extracted.
        assert sorted(l["name"] for l in out.get("languages") or []) == ["Anglais", "Français"]

    def test_dedupes_ocr_ligature_variants(self):
        # OCR/Unicode: "ﬁ" (U+FB01) is a single codepoint for "fi" used by some PDF extractors.
        data = {
            "name": "X", "title": "Dev", "formations": [], "experiences": [],
            "skills": [
                {"category": "Certifications", "items": [
                    "Oracle Certified Associate Java SE 8",
                    "Oracle Certiﬁed Associate Java SE 8",  # U+FB01 ligature
                ]},
            ],
        }
        out = _postprocess_skills_into_languages_and_certifications(data)
        certs = out.get("certifications") or []
        assert len(certs) == 1, f"expected 1 cert after ligature dedup, got {certs}"
        assert "certified" in certs[0].lower()

    def test_noop_when_top_level_fields_already_filled(self):
        data = {
            "name": "X",
            "title": "Dev",
            "formations": [],
            "skills": [
                {"category": "Backend", "items": ["Java", "Spring"]},
            ],
            "experiences": [],
            "languages": [{"name": "Français", "level": "courant"}],
            "certifications": ["PMP"],
        }
        out = _postprocess_skills_into_languages_and_certifications(data)
        assert out["languages"] == [{"name": "Français", "level": "courant"}]
        assert out["certifications"] == ["PMP"]
        # Skills category is untouched.
        assert out["skills"] == [{"category": "Backend", "items": ["Java", "Spring"]}]

    def test_does_not_mutate_input(self):
        data = {
            "name": "X",
            "title": "Dev",
            "formations": [],
            "skills": [{"category": "Langues", "items": ["Arabe 5 Anglais 4 Java Spring"]}],
            "experiences": [],
        }
        snapshot = json.dumps(data, sort_keys=True)
        _postprocess_skills_into_languages_and_certifications(data)
        assert json.dumps(data, sort_keys=True) == snapshot


# ---------------------------------------------------------------------------
# Renderer integration: the "Formation & Diplômes" sidebar
# ---------------------------------------------------------------------------

WORKER_ROOT = Path(__file__).resolve().parents[1]
RENDERER_PATH = WORKER_ROOT / "renderer" / "whub_cv_renderer.py"


def _render_pdf(data: dict) -> bytes:
    """Run the real renderer in a subprocess and return the PDF bytes."""
    if not DEFAULT_WHUB_ASSETS_DIR.exists() or not DEFAULT_WHUB_FONTS_DIR.exists():
        pytest.skip("W hub assets or Poppins fonts not present in the test env")
    workdir = WORKER_ROOT / "tests" / "_tmp_renderer"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    input_path = workdir / "input.json"
    output_path = workdir / "output.pdf"
    input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    env = {
        **__import__("os").environ,
        "WHUB_ASSETS_DIR": str(DEFAULT_WHUB_ASSETS_DIR),
        "WHUB_FONTS_DIR": str(DEFAULT_WHUB_FONTS_DIR),
    }
    result = subprocess.run(
        [sys.executable, str(RENDERER_PATH), str(input_path), str(output_path)],
        text=True,
        capture_output=True,
        env=env,
        timeout=180,
    )
    assert result.returncode == 0, f"renderer failed: {result.stderr or result.stdout}"
    return output_path.read_bytes()


def _pdf_text(pdf_bytes: bytes) -> str:
    """Return plain text from a PDF using pdftotext (poppler-utils)."""
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        pytest.skip("pdftotext not installed")
    proc = subprocess.run(
        [pdftotext, "-layout", "-", "-"],
        input=pdf_bytes,
        capture_output=True,
        timeout=60,
    )
    return proc.stdout.decode("utf-8", errors="ignore")


@pytest.mark.renderer
class TestFormationDiplomesSidebar:
    def test_sidebar_groups_formations_certifications_and_languages(self):
        data = {
            "name": "IMED",
            "title": "Chef de Projet Technique Java / Développeur Senior",
            "formations": [
                {"date": "2016", "degree": "Ingénieur en Génie du Logiciel", "school": "ISI"},
                {"date": "2013", "degree": "Licence informatique", "school": "ISET"},
            ],
            "certifications": ["Oracle Certified Associate Java SE 8"],
            "languages": [
                {"name": "Arabe", "level": "natif"},
                {"name": "Français", "level": "courant"},
                {"name": "Anglais", "level": "technique"},
            ],
            "skills": [{"category": "Backend", "items": ["Java 17", "Spring Boot"]}],
            "experiences": [
                {
                    "date": "Novembre 2022 – janvier 2026",
                    "role": "Chef de Projet Technique",
                    "company_highlight": "BNP Parisbas",
                    "sections": [
                        {"heading": "Missions clés", "content": ["Pilotage des applications ALM."]},
                    ],
                }
            ],
        }
        pdf = _render_pdf(data)
        text = _pdf_text(pdf)
        # The new sidebar header is present.
        assert "FORMATION &" in text
        assert "DIPLÔMES" in text
        # All three sub-sections appear in the right column.
        assert "Certifications" in text
        # The certification text may wrap on two lines in the narrow sidebar column.
        normalised = re.sub(r"\s+", " ", text)
        assert "Oracle Certified Associate Java SE 8" in normalised
        assert "Langues" in text
        assert "Arabe" in text
        assert "Français" in text
        assert "Anglais" in text
        # Programming languages (Java 17, Spring Boot) are NOT in the right column.
        right_column = text.split("DIPLÔMES", 1)[-1] if "DIPLÔMES" in text else ""
        assert "Spring Boot" not in right_column
        # The skills column keeps the programming languages.
        assert "Java 17" in text
        assert "Spring Boot" in text

    def test_sidebar_drops_sub_sections_when_data_missing(self):
        data = {
            "name": "BOB",
            "title": "Dev",
            "formations": [{"date": "2020", "degree": "BSc", "school": "UPMC"}],
            "skills": [{"category": "Backend", "items": ["Python"]}],
            "experiences": [],
        }
        pdf = _render_pdf(data)
        text = _pdf_text(pdf)
        # New header is still there.
        assert "FORMATION &" in text
        # No certifications / no languages sub-headers in the right column.
        right_column = text.split("DIPLÔMES", 1)[-1] if "DIPLÔMES" in text else ""
        assert "Certifications" not in right_column
        assert "Langues" not in right_column
        # Diploma is still there.
        assert "BSc" in text
