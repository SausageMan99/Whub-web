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


def test_parse_source_skills_stops_at_formations_boundary():
    from src.skills_intelligence import parse_source_skills_section

    source = (FIXTURES / "olivier_hellowork_competences.txt").read_text(encoding="utf-8")

    parsed = parse_source_skills_section(source)
    flattened = [item for items in parsed.skills_by_category.values() for item in items]

    assert not any("ESME" in item for item in flattened)
    assert not any("Ingénieur en électronique" in item for item in flattened)
    assert not any("Centres d" in item or "Sport" in item for item in flattened)


def test_split_arrow_skill_items_handles_arrow_on_its_own_line():
    from src.skills_intelligence import _split_arrow_skill_items

    lines = [
        "Architecte logiciel / Direction technique",
        "➢",
        "Cloud: AWS, AZURE",
        "➢",
        "DevOps : GitLab CICD, Jenkins, Docker",
    ]

    assert _split_arrow_skill_items(lines) == [
        "Architecte logiciel / Direction technique",
        "Cloud: AWS, AZURE",
        "DevOps : GitLab CICD, Jenkins, Docker",
    ]


def test_parse_source_skills_maps_source_prefixes_to_whub_taxonomy():
    from src.skills_intelligence import parse_source_skills_section

    parsed = parse_source_skills_section(
        """
COMPÉTENCES
➢
Cloud: AWS, AZURE
➢
Sécurité: JWT, OAuth2, LDAP, OWASP
➢
Data bases: MySQL, SQLserver, PostegreSQL
➢
Système : Linux RHEL, UBUNTU, Windows
FORMATIONS
x
"""
    )

    assert parsed.skills_by_category == {
        "Cloud & DevOps": ["AWS", "Azure"],
        "Sécurité": ["JWT", "OAuth2", "LDAP", "OWASP"],
        "Bases de données": ["MySQL", "SQL Server", "PostgreSQL"],
        "Systèmes & Environnements": ["Linux RHEL", "Ubuntu", "Windows"],
    }


def test_parse_source_skills_classifies_architecture_and_methods_without_autres_dump():
    from src.skills_intelligence import parse_source_skills_section

    parsed = parse_source_skills_section(
        """
COMPÉTENCES
Architecte logiciel / Direction technique
➢
Architecture logicielle : Conception de solution, Urbanisation, Référentiel d’architecture, PaaS, IaaS, CaaS, EDA, EIP, SOA, programmation asynchrone
➢
TOGAF, C4, DDD, SAFE
FORMATIONS
x
"""
    )

    assert "Architecture & Conception" in parsed.skills_by_category
    assert "Méthodologies" in parsed.skills_by_category
    assert "SOA" in parsed.skills_by_category["Architecture & Conception"]
    assert "TOGAF" in parsed.skills_by_category["Méthodologies"]
    assert "DDD" in parsed.skills_by_category["Méthodologies"]


def test_parse_source_skills_extracts_spoken_language_tail():
    from src.skills_intelligence import parse_source_skills_section

    parsed = parse_source_skills_section(
        """
COMPÉTENCES
Cloud: AWS, Azure

Anglais
Lu, parlé, écrit

FORMATIONS
x
"""
    )

    assert parsed.languages == [{"name": "Anglais", "level": "Lu, parlé, écrit"}]
    flattened = [item for items in parsed.skills_by_category.values() for item in items]
    assert "Anglais" not in flattened
    assert "Lu" not in flattened
    assert "parlé" not in flattened
    assert "écrit" not in flattened


def test_parse_source_skills_classifies_unprefixed_methodology_line():
    from src.skills_intelligence import parse_source_skills_section

    parsed = parse_source_skills_section(
        """
COMPÉTENCES
TOGAF, C4, DDD, SAFE
FORMATIONS
x
"""
    )

    assert "Méthodologies" in parsed.skills_by_category
    assert parsed.skills_by_category["Méthodologies"] == ["TOGAF", "C4", "DDD", "SAFE"]


def test_build_display_skills_removes_global_duplicates_across_categories():
    from src.skills_intelligence import build_display_skills

    raw = [
        {"category": "Cloud / DevOps", "items": ["AWS", "Docker", "Kubernetes"]},
        {"category": "Autres", "items": ["Docker", "docker-compose", "SQLserver"]},
        {"category": "Bases de données", "items": ["SQL Server"]},
    ]

    display = build_display_skills(raw, source_text="")
    flattened = [(cat["category"], item) for cat in display for item in cat["items"]]

    assert sum(1 for _, item in flattened if item == "Docker") == 1
    assert sum(1 for _, item in flattened if item == "SQL Server") == 1
    assert any(cat == "Cloud & DevOps" and item == "Docker Compose" for cat, item in flattened)


def test_build_display_skills_reclassifies_autres_and_keeps_ratio_low():
    from src.skills_intelligence import build_display_skills

    raw = [
        {
            "category": "Autres",
            "items": ["JWT", "OAuth2", "LDAP", "X509", "OWASP", "Dynatrace", "Kibana", "Ubuntu"],
        }
    ]

    display = build_display_skills(raw, source_text="")
    categories = {cat["category"] for cat in display}

    assert "Sécurité" in categories
    assert "Observabilité" in categories
    assert "Systèmes & Environnements" in categories
    assert "Autres" not in categories


def test_apply_skills_intelligence_merges_source_and_llm_without_duplicates():
    from src.skills_intelligence import apply_skills_intelligence

    source = (FIXTURES / "olivier_hellowork_competences.txt").read_text(encoding="utf-8")
    data = {
        "skills": [
            {"category": "Autres", "items": ["AWS", "Docker", "SQLserver", "Anglais"]},
            {"category": "Cloud / DevOps", "items": ["AWS", "Kubernetes"]},
        ],
        "languages": [],
        "certifications": [],
    }

    out = apply_skills_intelligence(data, source)
    flattened = [item for cat in out["skills"] for item in cat["items"]]

    assert flattened.count("AWS") == 1
    assert "SQL Server" in flattened
    assert "Anglais" not in flattened
    assert out["languages"] == [{"name": "Anglais", "level": "Lu, parlé, écrit"}]
    assert not any(cat["category"].startswith("Autres — suite") for cat in out["skills"])


def test_source_gate_structured_data_applies_skills_intelligence_to_olivier_fixture():
    from src.structuring import _source_gate_structured_data

    source = (FIXTURES / "olivier_hellowork_competences.txt").read_text(encoding="utf-8")
    data = {
        "name": "OLIVIER",
        "title": "Architecte solution logiciel & technique",
        "formations": [],
        "skills": [
            {"category": "Autres", "items": ["AWS", "AZURE", "Docker", "SQLserver", "Anglais"]},
            {"category": "Cloud / DevOps", "items": ["AWS", "Docker", "Kubernetes"]},
        ],
        "languages": [],
        "certifications": [],
        "experiences": [],
    }

    out = _source_gate_structured_data(data, source)
    categories = [cat["category"] for cat in out["skills"]]
    flattened = [item for cat in out["skills"] for item in cat["items"]]

    assert "Autres — suite" not in categories
    assert "Autres — suite 2" not in categories
    assert "Cloud & DevOps" in categories
    assert "Bases de données" in categories
    assert flattened.count("AWS") == 1
    assert flattened.count("Docker") == 1
    assert "SQL Server" in flattened
    assert "Anglais" not in flattened
    assert out["languages"] == [{"name": "Anglais", "level": "Lu, parlé, écrit"}]


def test_source_gate_does_not_reinject_full_competences_block_when_atomic_terms_covered():
    from src.structuring import _source_gate_structured_data

    source = (FIXTURES / "olivier_hellowork_competences.txt").read_text(encoding="utf-8")
    data = {
        "skills": [
            {"category": "Cloud & DevOps", "items": ["AWS", "Azure", "Docker", "Kubernetes"]},
            {"category": "Sécurité", "items": ["JWT", "OAuth2", "LDAP", "OWASP"]},
            {"category": "Bases de données", "items": ["MySQL", "MongoDB", "Oracle", "SQL Server", "PostgreSQL"]},
        ],
        "languages": [{"name": "Anglais", "level": "Lu, parlé, écrit"}],
    }

    out = _source_gate_structured_data(data, source)
    flattened = [item for cat in out["skills"] for item in cat["items"]]

    assert not any("Direction d'équipes de développement, recrutement, roadmap" in item for item in flattened)
    assert not any("Cloud: AWS" in item for item in flattened)
    assert not any("Data bases:" in item for item in flattened)


def test_evaluate_skills_display_quality_flags_olivier_style_dump():
    from src.skills_intelligence import evaluate_skills_display_quality

    skills = [
        {"category": "Autres", "items": [f"item-{i}" for i in range(20)] + ["Docker"]},
        {"category": "Autres — suite 5", "items": ["AWS", "Docker"]},
        {"category": "Cloud & DevOps", "items": ["AWS", "Docker"]},
    ]

    issues = evaluate_skills_display_quality(skills)
    codes = {issue["code"] for issue in issues}

    assert "too_many_autres_items" in codes
    assert "continued_autres_category" in codes
    assert "duplicate_skill_items" in codes


def test_evaluate_skills_display_quality_flags_too_many_total_items():
    from src.skills_intelligence import evaluate_skills_display_quality

    skills = [
        {"category": "Outils & Environnements", "items": [f"item-{i}" for i in range(70)]},
    ]

    issues = evaluate_skills_display_quality(skills)
    codes = {issue["code"] for issue in issues}

    assert "too_many_skill_items" in codes


def test_evaluate_skills_display_quality_flags_autres_dominance_ratio():
    from src.skills_intelligence import evaluate_skills_display_quality

    skills = [
        {"category": "Backend", "items": ["C#", "ASP.NET"]},
        {"category": "Autres", "items": [f"item-{i}" for i in range(10)]},
    ]

    issues = evaluate_skills_display_quality(skills)
    codes = {issue["code"] for issue in issues}

    assert "autres_dominates_skills" in codes


def test_source_gate_attaches_skill_quality_warnings_for_bad_display():
    from src.structuring import _source_gate_structured_data

    source = "COMPÉTENCES\nAutre chose non classable " + ", ".join(f"item{i}" for i in range(70))
    data = {
        "skills": [{"category": "Autres — suite 5", "items": [f"item{i}" for i in range(70)]}],
        "languages": [],
        "certifications": [],
    }

    out = _source_gate_structured_data(data, source)
    warnings = out.get("_skill_quality_warnings") or []
    assert warnings
    assert any(
        w["code"] in {"too_many_skill_items", "too_many_autres_items", "continued_autres_category"}
        for w in warnings
    )
