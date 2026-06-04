from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from PIL import Image

from .config import DEFAULT_WHUB_RENDERER_PATH, settings


EXPECTED_ASSETS = {
    "img_0dcab6df734b.png": {
        "size": (1051, 398),
        "sha256": "433aa43c8707d67de8e74fcf02a015984b00a5979c6ee62631d83dcff74ccdfb",
    },
    "img_90df8f14aa40.png": {
        "size": (1192, 1192),
        "sha256": "fe0d6b69be079214fe39c1b590eb2444386d032fb80f48dfb95f6a5eb4c49131",
    },
}
EXPECTED_FONT_SHA256 = {
    "Regular": "7e65201e9b79159e2300267cc885e16c8dcef2424cdfa09a29bfb0980a94a7ba",
    "Bold": "983676516167748b74de6f4771fb384c664fd913acb8b471122ecacf5da5ea6c",
    "SemiBold": "d3bf1bdaf0550e83da9ac0b1d1d9fe6db086835a83aa28578e609a394b9a0286",
    "Light": "650ba57fa99d12ec40c31ccfb680be656be4497fbe14164617d67e32ffe9cd46",
}
REQUIRED_FONT_WEIGHTS = tuple(EXPECTED_FONT_SHA256)
REQUIRED_SUPABASE_SETTINGS = (
    "supabase_url",
    "supabase_anon_key",
    "worker_database_url",
    "cv_sources_bucket",
    "cv_renderer_inputs_bucket",
    "cv_finals_bucket",
    "cv_artifacts_bucket",
)


class StartupPreflightError(RuntimeError):
    """Raised when the worker cannot safely process CV jobs."""


def _require_non_empty_setting(worker_settings: Any, name: str) -> None:
    value = getattr(worker_settings, name, None)
    if name == "worker_database_url" and (value is None or str(value).strip() == ""):
        value = getattr(worker_settings, "worker_db_url", None)
    if value is None or str(value).strip() == "":
        raise StartupPreflightError(f"Configuration manquante: {name}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_renderer_exists(worker_settings: Any) -> Path:
    renderer_path = Path(worker_settings.whub_renderer_path)
    if not renderer_path.exists() or not renderer_path.is_file():
        raise StartupPreflightError(f"Renderer W hub manquant: {renderer_path}")

    repo_renderer_path = DEFAULT_WHUB_RENDERER_PATH
    if not repo_renderer_path.exists() or not repo_renderer_path.is_file():
        raise StartupPreflightError(f"Renderer W hub repo-local manquant: {repo_renderer_path}")

    try:
        same_path = renderer_path.resolve(strict=True) == repo_renderer_path.resolve(strict=True)
    except OSError:
        same_path = False
    if same_path:
        return renderer_path

    configured_sha256 = _sha256(renderer_path)
    repo_sha256 = _sha256(repo_renderer_path)
    if configured_sha256 != repo_sha256:
        raise StartupPreflightError(
            "Renderer W hub divergent: "
            f"configuré={renderer_path} sha256={configured_sha256}; "
            f"repo-local={repo_renderer_path} sha256={repo_sha256}. "
            "WHUB_RENDERER_PATH doit pointer vers le renderer repo-local ou un fichier strictement identique."
        )
    return renderer_path


def _assert_assets(worker_settings: Any) -> Path:
    assets_dir = Path(worker_settings.whub_assets_dir)
    for filename, expected in EXPECTED_ASSETS.items():
        path = assets_dir / filename
        if not path.exists() or not path.is_file():
            raise StartupPreflightError(f"Asset W hub manquant: {path}")
        with Image.open(path) as image:
            actual_size = image.size
        expected_size = expected["size"]
        if actual_size != expected_size:
            raise StartupPreflightError(
                f"Mauvais asset W hub {path}: {actual_size}, attendu {expected_size}"
            )
        actual_sha256 = _sha256(path)
        expected_sha256 = expected["sha256"]
        if actual_sha256 != expected_sha256:
            raise StartupPreflightError(
                "Asset W hub divergent: "
                f"{path} sha256={actual_sha256}; attendu sha256={expected_sha256}. "
                "WHUB_ASSETS_DIR doit pointer vers les assets W hub repo-local validés ou des fichiers strictement identiques."
            )
    return assets_dir


def _assert_fonts_match(fonts_dir: Path) -> None:
    for weight in REQUIRED_FONT_WEIGHTS:
        path = fonts_dir / f"Poppins-{weight}.ttf"
        if not path.exists() or not path.is_file():
            required = ", ".join(f"Poppins-{required_weight}.ttf" for required_weight in REQUIRED_FONT_WEIGHTS)
            raise StartupPreflightError(f"Fonts Poppins manquantes: {required} dans {fonts_dir}")
        actual_sha256 = _sha256(path)
        expected_sha256 = EXPECTED_FONT_SHA256[weight]
        if actual_sha256 != expected_sha256:
            raise StartupPreflightError(
                "Font Poppins divergente: "
                f"{path} sha256={actual_sha256}; attendu sha256={expected_sha256}. "
                "WHUB_FONTS_DIR doit pointer vers les fonts Poppins repo-local validées ou des fichiers strictement identiques."
            )


def _resolve_fonts(worker_settings: Any) -> tuple[Path, str]:
    configured_fonts_dir = Path(worker_settings.whub_fonts_dir)
    _assert_fonts_match(configured_fonts_dir)
    return configured_fonts_dir, "configured"


def _assert_supabase_settings(worker_settings: Any) -> None:
    for name in REQUIRED_SUPABASE_SETTINGS:
        _require_non_empty_setting(worker_settings, name)
    if not str(worker_settings.supabase_url).startswith(("http://", "https://")):
        raise StartupPreflightError("Configuration invalide: supabase_url doit être une URL HTTP(S)")


def run_startup_preflight(worker_settings: Any = settings) -> dict[str, str]:
    """Validate local renderer dependencies and required remote settings before polling.

    The returned report is safe to log: it contains paths and status labels only, never
    Supabase tokens or other secret values.
    """

    renderer_path = _assert_renderer_exists(worker_settings)
    assets_dir = _assert_assets(worker_settings)
    fonts_dir, fonts_source = _resolve_fonts(worker_settings)
    _assert_supabase_settings(worker_settings)

    return {
        "renderer": str(renderer_path),
        "assets_dir": str(assets_dir),
        "fonts_dir": str(fonts_dir),
        "fonts_source": fonts_source,
        "supabase": "configured",
    }
