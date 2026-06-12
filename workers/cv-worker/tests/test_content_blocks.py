from src.content_blocks import ContentBlock, SourceDocument, estimate_lines, stable_block_id


def test_stable_block_id_uses_type_order_and_text_fingerprint():
    block_id = stable_block_id(block_type="experience", source_order=3, text="Développement API Java")
    assert block_id.startswith("experience_003_")
    assert block_id == stable_block_id("experience", 3, "Développement API Java")


def test_estimate_lines_counts_wrapped_text():
    text = "Une ligne courte\n" + "mot " * 80
    assert estimate_lines(text, chars_per_line=60) >= 7


def test_content_block_preserves_text_verbatim():
    text = "Développement d'API REST en Java\nEnvironnement : Spring, AWS"
    block = ContentBlock.from_text(block_type="experience", source_order=1, page=2, text=text)
    assert block.text == text
    assert block.type == "experience"
    assert block.required is True
    assert block.estimated_lines > 0


def test_source_document_orders_blocks_by_source_order():
    b2 = ContentBlock.from_text("skills", 2, 1, "Java, AWS")
    b1 = ContentBlock.from_text("profile", 1, 1, "Développeur backend")
    doc = SourceDocument(blocks=[b2, b1])
    assert [b.source_order for b in doc.ordered_blocks()] == [1, 2]
