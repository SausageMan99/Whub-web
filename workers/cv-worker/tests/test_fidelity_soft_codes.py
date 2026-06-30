"""Tests for the hard vs soft fidelity policy in validate_source_fidelity.

2026-06-30: synthetic_technical_environment, source_coverage_missing_experience_item,
and headerless_experience_sections moved to SOFT_FIDELITY_CODES so the worker
delivers a draft instead of a hard fail when the same source profile can
score fidelity=0 on one run and draft_ready on the next.
"""

from src.structuring import (
    HARD_FIDELITY_CODES,
    SOFT_FIDELITY_CODES,
    validate_source_fidelity,
)
import pytest


SOURCE_SENIOR_LONG = (
    "Imed\n"
    "EXPÉRIENCES PROFESSIONNELLES\n"
    "2020 - 2024 — Chef de projet technique\n"
    "Société Générale — Direction des risques\n"
    "• Pilotage d'un programme de transformation SI\n"
    "• Coordination de 3 équipes mixtes onshore/offshore\n"
    "• Mise en place d'un dashboard de suivi temps réel\n"
    "2018 - 2020 — Architecte solutions\n"
    "BNP Paribas — IT Group\n"
    "• Conception d'architectures micro-services\n"
    "• Migration vers Kubernetes\n"
    "COMPÉTENCES\n"
    "Java, Spring Boot, Kubernetes, AWS, PostgreSQL\n"
)


def test_hard_codes_keep_blocking():
    assert "candidate_identity_term_exposed" in HARD_FIDELITY_CODES
    assert "contact_leak_in_structured_data" in HARD_FIDELITY_CODES
    assert "full_name_display" in HARD_FIDELITY_CODES


def test_soft_codes_include_synthetic_environment():
    assert "synthetic_technical_environment" in SOFT_FIDELITY_CODES
    assert "source_coverage_missing_experience_item" in SOFT_FIDELITY_CODES
    assert "headerless_experience_sections" in SOFT_FIDELITY_CODES


def test_soft_codes_never_contain_hard_codes():
    overlap = HARD_FIDELITY_CODES & SOFT_FIDELITY_CODES
    assert overlap == frozenset(), (
        "Hard codes must not overlap with soft codes: %r" % (overlap,)
    )


def test_synthetic_environment_does_not_raise():
    """The exact failure mode observed on CV Imed Ben Hassine 2026-06-30 12:05:48
    (fidelity_issues=['synthetic_technical_environment']) must now produce
    _fidelity_soft_warnings instead of raising."""
    data = {
        "name": "Imed",
        "title": "Chef de projet technique",
        "skills": [{"category": "Backend", "items": ["Java", "Spring"]}],
        "experiences": [
            {
                "date": "2020 - 2024",
                "role": "Chef de projet technique",
                "company_highlight": "Société Générale",
                "sections": [
                    {
                        "heading": "Environnement technique",  # not in source
                        "content": ["Java", "Spring", "Kubernetes"],
                    }
                ],
            }
        ],
    }
    validate_source_fidelity(SOURCE_SENIOR_LONG, data)
    assert "_fidelity_soft_warnings" in data
    codes = [w["code"] for w in data["_fidelity_soft_warnings"]]
    assert "synthetic_technical_environment" in codes


def test_candidate_identity_term_still_raises():
    """Hard identity leaks must keep hard-failing the job.

    We forge a forbidden-identity-term hit on the experience `role` by setting
    the term to a token that IS in the role text. The role check is skipped
    (see validate_source_fidelity: company_highlight/school/role are excluded
    from identity scanning), so we put the leak inside a `content` item to
    force candidate_identity_term_exposed.
    """
    from src.structuring import StructuringError
    data = {
        "name": "Imed",
        "title": "Chef de projet technique",
        "skills": [{"category": "Backend", "items": ["Java", "Spring"]}],
        "experiences": [
            {
                "date": "2020 - 2024",
                "role": "Chef de projet technique",
                "company_highlight": "Société Générale",
                "sections": [
                    {
                        "heading": "Missions",
                        "content": ["Pilotage SI par Imed Ben-Hassine"],
                    }
                ],
            }
        ],
    }
    with pytest.raises(StructuringError) as exc:
        validate_source_fidelity(
            SOURCE_SENIOR_LONG, data, forbidden_identity_terms=["Hassine"]
        )
    msg = str(exc.value)
    assert "candidate_identity_term_exposed" in msg
    assert "hard_count=" in msg
    assert "soft_count=" in msg
