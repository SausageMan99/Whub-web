from src.content_blocks import ContentBlock, SourceDocument
from src.source_coverage import build_coverage_ledger


def test_coverage_ledger_includes_required_experience_blocks():
    doc = SourceDocument(blocks=[
        ContentBlock.from_text("experience", 1, 0, "Développement API Java", required=True),
        ContentBlock.from_text("other", 2, 0, "Page 1/2", required=False),
    ])
    ledger = build_coverage_ledger(doc)
    assert [entry.block_id for entry in ledger.required_entries()] == [doc.blocks[0].id]


def test_coverage_ledger_uses_redacted_fingerprint_not_raw_text():
    doc = SourceDocument(blocks=[ContentBlock.from_text("experience", 1, 0, "Mission confidentielle Java", required=True)])
    ledger = build_coverage_ledger(doc)
    dumped = str(ledger.entries[0])
    assert "Mission confidentielle" not in dumped
    assert ledger.entries[0].fingerprint
