import unittest
from unittest.mock import patch
from src.main import _maybe_reuse_layout_only_structured_json


def _make_revision_comments():
    return [{
        "body": "remonter la dernière mission clé de la derniere page sur page 3",
        "comment_type": "revision",
        "resolved": False,
    }]


def _fake_client_with(rows):
    class FakeQuery:
        def eq(self, *_, **__):
            return self
        def execute(self):
            return type("Res", (), {"data": rows})()

    class FakeTable:
        def select(self, *_, **__):
            return FakeQuery()

    class FakeClient:
        def __init__(self, rows):
            self._rows = rows
        def table(self, *_, **__):
            return FakeTable()

    return FakeClient(rows)


class LayoutOnlyRevisionRoutingUnitTest(unittest.TestCase):
    def test_maybe_reuse_layout_only_structured_json_applies_routing(self):
        current_version = {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "version_number": 44,
            "structured_json": {
                "name": "PHILIPPE",
                "title": "Fullstack Developer (Java / React)",
                "formations": [],
                "skills": [],
                "experiences": [],
            },
            "qa_report": {"pages": 4, "layout_issues": [{"code": "last_page_sparse", "page": 4}], "passed": False},
        }

        sink: dict = {}
        fake_client = _fake_client_with([current_version])
        with patch("src.main.emit_event") as mock_emit:
            applied = _maybe_reuse_layout_only_structured_json(
                client=fake_client,
                request_id="req-1",
                current_version_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                revision_comments=_make_revision_comments(),
                effective_first_name="PHILIPPE",
                timings={},
                structured_sink=sink,
            )

        self.assertTrue(applied)
        self.assertTrue(sink.get("layout_only_active"))
        self.assertEqual(sink.get("structured"), current_version["structured_json"])
        event_types = [c.args[1] for c in mock_emit.call_args_list if len(c.args) >= 2]
        self.assertIn("layout_revision_reused_structured_json", event_types)

    def test_maybe_reuse_layout_only_skips_when_no_layout_keywords(self):
        sink: dict = {}
        with patch("src.main.emit_event") as mock_emit, \
             patch("src.main.client") as mock_client:
            applied = _maybe_reuse_layout_only_structured_json(
                client=mock_client,
                request_id="req-1",
                current_version_id="current-1",
                revision_comments=[{
                    "body": "corriger le texte de la mission",
                    "comment_type": "revision",
                    "resolved": False,
                }],
                effective_first_name="JEAN",
                timings={},
                structured_sink=sink,
            )

        self.assertFalse(applied)
        self.assertFalse(sink.get("layout_only_active"))
        event_types = [c.args[1] for c in mock_emit.call_args_list if len(c.args) >= 2]
        self.assertNotIn("layout_revision_reused_structured_json", event_types)

    def test_maybe_reuse_layout_only_skips_when_current_version_missing(self):
        sink: dict = {}
        with patch("src.main.emit_event") as mock_emit, \
             patch("src.main.client") as mock_client:
            applied = _maybe_reuse_layout_only_structured_json(
                client=mock_client,
                request_id="req-1",
                current_version_id=None,
                revision_comments=_make_revision_comments(),
                effective_first_name="JEAN",
                timings={},
                structured_sink=sink,
            )

        self.assertFalse(applied)
        self.assertFalse(sink.get("layout_only_active"))
        event_types = [c.args[1] for c in mock_emit.call_args_list if len(c.args) >= 2]
        self.assertNotIn("layout_revision_reused_structured_json", event_types)

    def test_no_current_version_falls_back(self):
        self.skipTest("covered by current_version missing case")

    def test_content_revision_does_not_apply(self):
        self.skipTest("covered by no layout keywords case")


if __name__ == "__main__":
    unittest.main()
