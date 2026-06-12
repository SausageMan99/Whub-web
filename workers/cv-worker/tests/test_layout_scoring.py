from src.layout_scoring import LayoutScore, choose_best_layout_score


def test_choose_best_rejects_contact_leak_even_if_visual_score_good():
    bad = LayoutScore(variant="bad", missing_required_blocks=0, contact_hits=1, identity_hits=0, sparse_pages=0, dense_pages=0, page_count=2)
    good = LayoutScore(variant="good", missing_required_blocks=0, contact_hits=0, identity_hits=0, sparse_pages=1, dense_pages=0, page_count=3)
    assert choose_best_layout_score([bad, good]).variant == "good"


def test_missing_required_blocks_is_worse_than_sparse_page():
    missing = LayoutScore(variant="missing", missing_required_blocks=1, contact_hits=0, identity_hits=0, sparse_pages=0, dense_pages=0, page_count=2)
    sparse = LayoutScore(variant="sparse", missing_required_blocks=0, contact_hits=0, identity_hits=0, sparse_pages=1, dense_pages=0, page_count=3)
    assert choose_best_layout_score([missing, sparse]).variant == "sparse"
