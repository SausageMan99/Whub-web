#!/usr/bin/env python3
"""Fail-fast preflight for packaged W hub renderer assets and fonts."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from PIL import Image

WORKER_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = WORKER_ROOT / "assets" / "whub"
FONTS_DIR = WORKER_ROOT / "assets" / "fonts" / "poppins"
EXPECTED_IMAGES = {
    "img_0dcab6df734b.png": {
        "size": (1051, 398),
        "sha256": "433aa43c8707d67de8e74fcf02a015984b00a5979c6ee62631d83dcff74ccdfb",
    },
    "img_90df8f14aa40.png": {
        "size": (1192, 1192),
        "sha256": "fe0d6b69be079214fe39c1b590eb2444386d032fb80f48dfb95f6a5eb4c49131",
    },
}
EXPECTED_FONTS = {
    "Regular": "7e65201e9b79159e2300267cc885e16c8dcef2424cdfa09a29bfb0980a94a7ba",
    "Bold": "983676516167748b74de6f4771fb384c664fd913acb8b471122ecacf5da5ea6c",
    "SemiBold": "d3bf1bdaf0550e83da9ac0b1d1d9fe6db086835a83aa28578e609a394b9a0286",
    "Light": "650ba57fa99d12ec40c31ccfb680be656be4497fbe14164617d67e32ffe9cd46",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    for filename, expected in EXPECTED_IMAGES.items():
        path = ASSETS_DIR / filename
        if not path.exists():
            fail(f"missing W hub asset: {path}")
        actual_size = Image.open(path).size
        expected_size = expected["size"]
        if actual_size != expected_size:
            fail(f"invalid dimensions for {path}: {actual_size}, expected {expected_size}")
        actual_sha256 = sha256(path)
        expected_sha256 = expected["sha256"]
        if actual_sha256 != expected_sha256:
            fail(f"invalid W hub asset hash for {path}: {actual_sha256}, expected {expected_sha256}")
        print(f"OK image {path.relative_to(WORKER_ROOT)} {actual_size[0]}x{actual_size[1]} sha256={actual_sha256}")

    for weight, expected_sha256 in EXPECTED_FONTS.items():
        path = FONTS_DIR / f"Poppins-{weight}.ttf"
        if not path.exists():
            fail(f"missing Poppins font: {path}")
        actual_sha256 = sha256(path)
        if actual_sha256 != expected_sha256:
            fail(f"invalid Poppins font hash for {path}: {actual_sha256}, expected {expected_sha256}")
        print(f"OK font {path.relative_to(WORKER_ROOT)} sha256={actual_sha256}")


if __name__ == "__main__":
    main()
