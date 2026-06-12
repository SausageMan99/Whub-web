from src.block_extraction import VisualTextBlock, blocks_to_content_blocks, sort_visual_blocks, is_probable_footer


def test_sort_visual_blocks_orders_by_page_y_then_x():
    blocks = [
        VisualTextBlock(page=1, bbox=(300, 100, 500, 130), text="Right"),
        VisualTextBlock(page=1, bbox=(50, 100, 250, 130), text="Left"),
        VisualTextBlock(page=0, bbox=(50, 500, 250, 530), text="Page zero"),
    ]
    assert [b.text for b in sort_visual_blocks(blocks)] == ["Page zero", "Left", "Right"]


def test_probable_footer_detects_page_marker():
    assert is_probable_footer("Page 1/3") is True
    assert is_probable_footer("1 / 4") is True
    assert is_probable_footer("Développeur Java") is False


def test_blocks_to_content_blocks_marks_footer_not_required():
    visual = [
        VisualTextBlock(page=0, bbox=(50, 50, 500, 100), text="Développeur Java"),
        VisualTextBlock(page=0, bbox=(50, 760, 500, 780), text="Page 1/3"),
    ]
    content = blocks_to_content_blocks(visual)
    assert content[0].required is True
    assert content[1].required is False
    assert content[1].type == "other"
