import unittest
from src.structuring import compact_extracted_text


class CompactExtractedTextTest(unittest.TestCase):
    def test_preserves_unique_content_lines(self):
        source = "  EXPÉRIENCE  \n\n\nMission A\nStack: Python  \n\nFormation\n"
        compacted = compact_extracted_text(source)
        self.assertIn("EXPÉRIENCE", compacted)
        self.assertIn("Mission A", compacted)
        self.assertIn("Stack: Python", compacted)
        self.assertIn("Formation", compacted)

    def test_collapses_excess_blank_lines_without_merging_sections(self):
        source = "Compétences\n\n\n\nExpériences\n\n\nFormation"
        compacted = compact_extracted_text(source)
        self.assertNotIn("\n\n\n", compacted)
        self.assertEqual(compacted, "Compétences\n\nExpériences\n\nFormation")

    def test_keeps_repeated_non_empty_lines_to_avoid_content_loss(self):
        source = "Java\nJava\nJava\n"
        compacted = compact_extracted_text(source)
        self.assertEqual(compacted, "Java\nJava\nJava")


if __name__ == "__main__":
    unittest.main()
