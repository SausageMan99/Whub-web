from src.content_blocks import ContentBlock, SourceDocument
from src.source_coverage import build_coverage_ledger, compare_required_block_coverage


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


def test_compare_required_block_coverage_passes_when_tokens_present():
    block = ContentBlock.from_text("experience", 1, 0, "Développement API Java Spring AWS", required=True)
    missing = compare_required_block_coverage(SourceDocument(blocks=[block]), "API Java Spring AWS Développement")
    assert missing == []


def test_compare_required_block_coverage_fails_when_experience_missing():
    block = ContentBlock.from_text("experience", 1, 0, "Développement API Java Spring AWS", required=True)
    missing = compare_required_block_coverage(SourceDocument(blocks=[block]), "Formation école ingénieur")
    assert missing == [{"block_id": block.id, "block_type": "experience", "source_order": 1}]


def test_compare_ignores_not_required_footer():
    block = ContentBlock.from_text("other", 1, 0, "Page 1/2", required=False)
    assert compare_required_block_coverage(SourceDocument(blocks=[block]), "") == []
