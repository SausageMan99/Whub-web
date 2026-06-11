from __future__ import annotations

from copy import deepcopy
from typing import Any

from ._inner.packing import (
    _content_items,
    estimate_experience_units,
    compute_experience_page_breaks,
    build_layout_packing_options,
    assert_packing_preserves_experience_content,
)

__all__ = [
    "estimate_experience_units",
    "compute_experience_page_breaks",
    "build_layout_packing_options",
    "assert_packing_preserves_experience_content",
]