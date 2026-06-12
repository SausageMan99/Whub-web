from src.content_blocks import ContentBlock, SourceDocument
from src.block_sanitizer import sanitize_block, sanitize_document


def block(text: str) -> ContentBlock:
    return ContentBlock.from_text("experience", 1, 0, text)


def test_sanitize_block_removes_email_phone_and_linkedin():
    source = block("Contact: alice@test.fr 06 12 34 56 78 linkedin.com/in/alice\nDéveloppement Java")
    result = sanitize_block(source, candidate_first_name="Alice", forbidden_identity_terms=[])
    assert "@" not in result.block.text
    assert "06 12" not in result.block.text
    assert "linkedin.com/in" not in result.block.text
    assert "Développement Java" in result.block.text
    assert result.report["removed_email_count"] == 1
    assert result.report["removed_phone_count"] == 1
    assert result.report["removed_linkedin_count"] == 1


def test_sanitize_block_preserves_business_at_symbol():
    source = block("Projet Th@Bot : automatisation support client")
    result = sanitize_block(source, candidate_first_name="Alice", forbidden_identity_terms=[])
    assert "Th@Bot" in result.block.text
    assert result.report["removed_email_count"] == 0


def test_sanitize_document_never_reports_raw_contact_values():
    doc = SourceDocument(blocks=[block("alice@test.fr\nMission Java")])
    result = sanitize_document(doc, candidate_first_name="Alice", forbidden_identity_terms=[])
    dumped = str(result.report)
    assert "alice@test.fr" not in dumped
    assert result.document.blocks[0].text.strip() == "Mission Java"
