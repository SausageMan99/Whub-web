"""TDD: a block whose only non-empty lines are recognised section headings
(e.g. bare 'EDUCATION', 'FORMATIONS', 'COMPÉTENCES', 'CERTIFICATIONS') must
be coalesced with a neighbouring content block before Hermes is called.

The original bug: a 10-char "EDUCATION" block was sent to the model on its
own. The model returned malformed JSON and the worker failed with
structuring_invalid_json on every CV long enough to trigger block splitting.
"""
import unittest

from src.structuring import split_cv_text_into_blocks


def _is_heading_only_block(block: dict) -> bool:
    """A block is 'heading-only' if it has exactly one non-empty line AND that
    line is a recognised section heading (e.g. bare 'EDUCATION', 'FORMATIONS',
    'COMPÉTENCES'). These blocks are useless on their own and must be coalesced
    with a neighbouring content block.

    We require the line to be all-uppercase (or uppercase-with-accents) so that
    content lines such as 'Profil cloud data' are not mistaken for headings.
    """
    from src.structuring import _heading_kind
    non_empty = [line.strip() for line in block["text"].splitlines() if line.strip()]
    if len(non_empty) != 1:
        return False
    line = non_empty[0]
    if len(line) > 50:
        return False
    if _heading_kind(line) is None:
        return False
    # Strip accents and check uppercase: an actual heading is in caps.
    import unicodedata
    folded = "".join(c for c in unicodedata.normalize("NFD", line) if unicodedata.category(c) != "Mn")
    return folded == folded.upper() and any(c.isalpha() for c in folded)


class BlockCoalescingTest(unittest.TestCase):
    def test_heading_only_skills_block_does_not_remain_alone(self):
        # "COMPÉTENCES" alone with no items beneath it must be merged with
        # the next experience block, not sent alone to the model.
        text = (
            "Jean Dupont\n"
            "Architecte\n"
            "\n"
            "COMPÉTENCES\n"
            "\n"
            "EXPÉRIENCES PROFESSIONNELLES\n"
            "2022 - Aujourd'hui Architecte chez ACME\n"
            "Missions: cadrage\n"
        )
        blocks = split_cv_text_into_blocks(text)
        heading_only = [b for b in blocks if _is_heading_only_block(b)]
        self.assertEqual(
            heading_only, [],
            f"heading-only blocks must be coalesced, found: "
            f"{[(b['kind'], b['text'][:60]) for b in heading_only]}"
        )
        flat = "\n".join(b["text"] for b in blocks)
        self.assertIn("ACME", flat)

    def test_heading_only_education_block_between_experiences_is_coalesced(self):
        text = (
            "Jean Dupont\n"
            "Architecte\n"
            "\n"
            "EXPÉRIENCES PROFESSIONNELLES\n"
            "2022 - Aujourd'hui Architecte chez ACME\n"
            "Missions: cadrage\n"
            "\n"
            "EDUCATION\n"
            "\n"
            "2021 - 2022 Tech Lead chez BETA\n"
            "Missions: backend\n"
        )
        blocks = split_cv_text_into_blocks(text)
        heading_only = [b for b in blocks if _is_heading_only_block(b)]
        self.assertEqual(
            heading_only, [],
            f"heading-only blocks must be coalesced, found: "
            f"{[(b['kind'], b['text'][:60]) for b in heading_only]}"
        )
        flat = "\n".join(b["text"] for b in blocks)
        self.assertIn("ACME", flat)
        self.assertIn("BETA", flat)

    def test_multiple_short_headings_are_coalesced_with_neighbours(self):
        text = (
            "Jean Dupont\n"
            "Architecte\n"
            "\n"
            "PROFIL\n"
            "Profil cloud data\n"
            "\n"
            "COMPÉTENCES\n"
            "\n"
            "FORMATIONS\n"
            "\n"
            "EXPÉRIENCES PROFESSIONNELLES\n"
            "2022 - Aujourd'hui Architecte chez ACME\n"
            "Missions: cadrage architecture cloud\n"
            "\n"
            "LANGUES\n"
            "\n"
            "CERTIFICATIONS\n"
            "\n"
            "2021 - 2022 Tech Lead chez BETA\n"
            "Missions: backend\n"
        )
        blocks = split_cv_text_into_blocks(text)
        heading_only = [b for b in blocks if _is_heading_only_block(b)]
        self.assertEqual(
            heading_only, [],
            f"heading-only blocks must be coalesced, found: "
            f"{[(b['kind'], b['text'][:60]) for b in heading_only]}"
        )
        # Both experiences and the profile must survive.
        flat = "\n".join(b["text"] for b in blocks)
        self.assertIn("ACME", flat)
        self.assertIn("BETA", flat)
        self.assertIn("Profil cloud data", flat)

    def test_substantial_education_block_with_content_survives(self):
        # A real "EDUCATION" block with at least one content line below the
        # heading must remain a separate block (the heading IS its first line,
        # so the block is NOT heading-only).
        text = (
            "Jean Dupont\n"
            "Architecte\n"
            "\n"
            "EDUCATION\n"
            "2015 - 2017 Master informatique, Université Paris\n"
        )
        blocks = split_cv_text_into_blocks(text)
        flat = "\n".join(b["text"] for b in blocks)
        self.assertIn("Master informatique", flat)
        # The education heading and the degree should live in the same block
        # (the heading-only filter doesn't strip it because the block has
        # content lines beyond the heading).
        self.assertFalse(
            any(_is_heading_only_block(b) for b in blocks),
            "no block should be heading-only in this realistic CV",
        )


if __name__ == "__main__":
    unittest.main()
