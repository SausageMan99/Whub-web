"""Tests for the W hub skills intelligence layer.

Reproduces the Olivier/Baulier dense-skills dump bug and the deterministic
parser/deduplicator/taxonomy pass that fixes it.
"""
from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault(
    "WORKER_DB_URL",
    "postgresql://whub_worker:***@localhost:5432/postgres",
)

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_hellowork_arrow_skills_splits_isolated_arrow_bullets():
    from src.skills_intelligence import parse_source_skills_section

    source = (FIXTURES / "olivier_hellowork_competences.txt").read_text(encoding="utf-8")

    parsed = parse_source_skills_section(source)

    assert "Cloud & DevOps" in parsed.skills_by_category
    assert "Sécurité" in parsed.skills_by_category
    assert "Bases de données" in parsed.skills_by_category
    assert "Systèmes & Environnements" in parsed.skills_by_category
    assert "Architecture & Conception" in parsed.skills_by_category

    assert "AWS" in parsed.skills_by_category["Cloud & DevOps"]
    assert "Azure" in parsed.skills_by_category["Cloud & DevOps"]
    assert "Kubernetes" in parsed.skills_by_category["Cloud & DevOps"]
    assert "JWT" in parsed.skills_by_category["Sécurité"]
    assert "PostgreSQL" in parsed.skills_by_category["Bases de données"]
    assert "Windows" in parsed.skills_by_category["Systèmes & Environnements"]

    assert parsed.languages == [{"name": "Anglais", "level": "Lu, parlé, écrit"}]

    flattened = [item for items in parsed.skills_by_category.values() for item in items]
    assert not any("➢" in item for item in flattened)
    assert "Anglais" not in flattened
    assert "Lu" not in flattened
    assert "parlé" not in flattened
    assert "écrit" not in flattened
