#!/usr/bin/env python3
"""Fail-fast preflight for packaged W hub renderer assets and fonts."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

WORKER_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = WORKER_ROOT / "assets" / "whub"
FONTS_DIR = WORKER_ROOT / "assets" / "fonts" / "poppins"
EXPECTED_IMAGES = {
    "img_0dcab6df734b.png": (1051, 398),
    "img_90df8f14aa40.png": (1192, 1192),
}
EXPECTED_FONTS = ["Regular", "Bold", "SemiBold", "Light"]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    for filename, expected_size in EXPECTED_IMAGES.items():
        path = ASSETS_DIR / filename
        if not path.exists():
            fail(f"missing W hub asset: {path}")
        actual_size = Image.open(path).size
        if actual_size != expected_size:
            fail(f"invalid dimensions for {path}: {actual_size}, expected {expected_size}")
        print(f"OK image {path.relative_to(WORKER_ROOT)} {actual_size[0]}x{actual_size[1]}")

    for weight in EXPECTED_FONTS:
        path = FONTS_DIR / f"Poppins-{weight}.ttf"
        if not path.exists():
            fail(f"missing Poppins font: {path}")
        if path.stat().st_size <= 0:
            fail(f"empty Poppins font: {path}")
        print(f"OK font {path.relative_to(WORKER_ROOT)}")


if __name__ == "__main__":
    main()
