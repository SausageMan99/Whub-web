import pytest

from src.qa import _is_experience_sparse_metric


def test_is_experience_sparse_metric_returns_true_for_v45_regression_class():
    metric = {
        "page": 2,
        "used_ratio": 0.41,
        "char_count": 1411,
        "has_experience_heading": True,
        "starts_with_suite": False,
    }
    assert _is_experience_sparse_metric(metric, page_count=5) is True


def test_is_experience_sparse_metric_returns_true_for_45_percent_experience_page():
    metric = {
        "page": 4,
        "used_ratio": 0.45,
        "char_count": 1616,
        "has_experience_heading": True,
        "starts_with_suite": False,
    }
    assert _is_experience_sparse_metric(metric, page_count=5) is True


def test_is_experience_sparse_metric_returns_false_for_first_page():
    metric = {
        "page": 1,
        "used_ratio": 0.58,
        "char_count": 967,
        "has_experience_heading": True,
        "starts_with_suite": False,
    }
    assert _is_experience_sparse_metric(metric, page_count=5) is False


def test_is_experience_sparse_metric_returns_false_for_last_page():
    metric = {
        "page": 5,
        "used_ratio": 0.41,
        "char_count": 1322,
        "has_experience_heading": True,
        "starts_with_suite": False,
    }
    assert _is_experience_sparse_metric(metric, page_count=5) is False


def test_is_experience_sparse_metric_returns_false_for_non_experience_page():
    metric = {
        "page": 2,
        "used_ratio": 0.41,
        "char_count": 1411,
        "has_experience_heading": False,
        "starts_with_suite": False,
    }
    assert _is_experience_sparse_metric(metric, page_count=5) is False


def test_is_experience_sparse_metric_returns_false_for_well_filled_experience_page():
    metric = {
        "page": 3,
        "used_ratio": 0.63,
        "char_count": 2007,
        "has_experience_heading": True,
        "starts_with_suite": False,
    }
    assert _is_experience_sparse_metric(metric, page_count=5) is False


def test_is_experience_sparse_metric_returns_false_when_short_doc():
    metric = {
        "page": 2,
        "used_ratio": 0.41,
        "char_count": 1411,
        "has_experience_heading": True,
        "starts_with_suite": False,
    }
    assert _is_experience_sparse_metric(metric, page_count=2) is False
