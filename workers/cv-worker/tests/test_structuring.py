import json
from unittest.mock import patch

import pytest

from src.structuring import (
    compact_extracted_text,
    assert_no_contact_in_json,
    build_whub_json,
    _extract_json,
    StructuringError,
    REQUIRED_TOP_LEVEL_KEYS,
)


class TestCompactExtractedText:
    def test_dedup_blank_lines(self):
        source = "Line 1\n\n\n\nLine 2\n\n\nLine 3"
        result = compact_extracted_text(source)
        assert "\n\n\n" not in result
        assert result == "Line 1\n\nLine 2\n\nLine 3"

    def test_preserves_non_empty_lines(self):
        source = "A\nB\nC"
        assert compact_extracted_text(source) == "A\nB\nC"

    def test_strips_trailing_whitespace_per_line(self):
        source = "  spaced out  \n\n  another  "
        assert compact_extracted_text(source) == "spaced out\n\nanother"

    def test_normalizes_crlf(self):
        source = "A\r\nB\rC"
        assert compact_extracted_text(source) == "A\nB\nC"


class TestAssertNoContactInJson:
    def test_raises_on_email(self):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        data["experiences"] = [{"date": "2024", "role": "Dev", "sections": [{"heading": "Contact", "content": ["jean@example.com"]}]}]
        with pytest.raises(StructuringError, match="Coordonnées"):
            assert_no_contact_in_json(data)

    def test_raises_on_linkedin(self):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        data["description"] = "Profil linkedin/in/jean"
        with pytest.raises(StructuringError, match="Coordonnées"):
            assert_no_contact_in_json(data)

    def test_raises_on_phone(self):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        data["experiences"] = [{"date": "2024", "role": "Dev", "sections": [{"heading": "Contact", "content": ["+33 6 12 34 56 78"]}]}]
        with pytest.raises(StructuringError, match="Coordonnées"):
            assert_no_contact_in_json(data)

    def test_raises_on_github(self):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        data["skills"] = [{"category": "Web", "items": ["github.com/jean"]}]
        with pytest.raises(StructuringError, match="Coordonnées"):
            assert_no_contact_in_json(data)

    def test_passes_without_contact(self):
        data = {
            "name": "JEAN",
            "title": "Dev",
            "formations": [{"date": "2020", "degree": "Master", "school": "Uni"}],
            "skills": [{"category": "Langages", "items": ["Python"]}],
            "experiences": [{"date": "2024", "role": "Dev", "sections": []}],
        }
        assert_no_contact_in_json(data)  # no raise


class TestExtractJson:
    def test_extracts_fenced_json(self):
        raw = '```json\n{"name":"A","title":"B","formations":[],"skills":[],"experiences":[]}\n```'
        result = _extract_json(raw)
        assert result["name"] == "A"

    def test_extracts_bare_json(self):
        raw = 'Some text before\n{"name":"A","title":"B","formations":[],"skills":[],"experiences":[]}\nAfter'
        result = _extract_json(raw)
        assert result["name"] == "A"

    def test_raises_when_required_keys_missing(self):
        raw = '{"name":"A","title":"B","formations":[],"skills":[]}'  # missing experiences
        with pytest.raises(StructuringError, match="clés manquantes"):
            _extract_json(raw)

    def test_raises_when_experiences_not_list(self):
        raw = '{"name":"A","title":"B","formations":[],"skills":[],"experiences":"nope"}'
        with pytest.raises(StructuringError, match="doit être une liste"):
            _extract_json(raw)

    def test_raises_on_invalid_json(self):
        raw = "not json at all"
        with pytest.raises(StructuringError, match="JSON exploitable"):
            _extract_json(raw)


class TestBuildWHubJson:
    def _make_runner(self, data: dict):
        def runner(prompt: str, timeout: int):
            return 0, json.dumps(data, ensure_ascii=False), ""
        return runner

    def test_build_whub_json_returns_all_required_keys(self):
        data = {
            "name": "Jean",
            "title": "Architecte",
            "formations": [{"date": "2020", "degree": "Master", "school": "Uni"}],
            "skills": [{"category": "Cloud", "items": ["AWS"]}],
            "experiences": [{"date": "2024", "role": "Lead", "sections": []}],
        }
        result = build_whub_json("some cv text\n" * 100, "", [], "Jean", hermes_runner=self._make_runner(data))
        assert REQUIRED_TOP_LEVEL_KEYS.issubset(set(result.keys()))
        assert result["name"] == "JEAN"
        assert result["title"] == "Architecte"

    def test_build_whub_json_applies_candidate_first_name(self):
        data = {
            "name": "Wrong",
            "title": "Dev",
            "formations": [],
            "skills": [],
            "experiences": [],
        }
        result = build_whub_json("cv text\n" * 100, "", [], "Pierre", hermes_runner=self._make_runner(data))
        assert result["name"] == "PIERRE"

    def test_build_whub_json_raises_on_hermes_failure(self):
        def bad_runner(prompt: str, timeout: int):
            return 1, "", "Hermes crashed"

        with pytest.raises(StructuringError, match="Hermes"):
            build_whub_json("cv text\n" * 100, "", [], hermes_runner=bad_runner)

    def test_build_whub_json_raises_on_contact_in_response(self):
        data = {
            "name": "Jean",
            "title": "Dev",
            "formations": [],
            "skills": [],
            "experiences": [{"date": "2024", "role": "Dev", "sections": [{"heading": "Contact", "content": ["jean@example.com"]}]}],
        }
        with pytest.raises(StructuringError, match="Coordonnées"):
            build_whub_json("cv text\n" * 100, "", [], hermes_runner=self._make_runner(data))

    def test_build_whub_json_uses_long_cv_mode_when_text_exceeds_threshold(self):
        calls = []

        def tracking_runner(prompt: str, timeout: int):
            calls.append(prompt)
            return 0, json.dumps({
                "name": "Jean", "title": "Dev",
                "formations": [], "skills": [], "experiences": [],
            }, ensure_ascii=False), ""

        long_text = "PROFIL\nJean architecte\n\nEXPÉRIENCES\n2022 ACME\n" + ("ligne acme\n" * 30) + "\n2021 BETA\n" + ("ligne beta\n" * 30)
        build_whub_json(long_text, "", [], "Jean", long_cv_threshold=80, hermes_runner=tracking_runner)
        assert len(calls) >= 2

    def test_build_whub_json_synthesis_mode_complete(self):
        data = {
            "name": "Jean", "title": "Dev",
            "formations": [], "skills": [], "experiences": [],
        }
        result = build_whub_json("cv text\n" * 100, "", [], hermes_runner=self._make_runner(data), synthesis_mode="complete")
        assert result["synthesis_policy"]["mode"] == "complete"
