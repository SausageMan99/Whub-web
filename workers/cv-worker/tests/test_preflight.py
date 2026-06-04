from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from src.config import (
    DEFAULT_WHUB_ASSETS_DIR,
    DEFAULT_WHUB_FONTS_DIR,
    DEFAULT_WHUB_RENDERER_PATH,
    LEGACY_WHUB_RENDERER_PATH,
    Settings,
)
from src.preflight import StartupPreflightError, run_startup_preflight


def _settings(tmp_path: Path, renderer: Path | None = None, assets_dir: Path | None = None, fonts_dir: Path | None = None):
    return SimpleNamespace(
        whub_renderer_path=str(renderer or tmp_path / "renderer.py"),
        whub_assets_dir=str(assets_dir or tmp_path / "assets"),
        whub_fonts_dir=str(fonts_dir or tmp_path / "fonts"),
        supabase_url="https://example.supabase.co",
        supabase_anon_key="test-anon-key",
        worker_db_url="postgresql://whub_worker:test@localhost:5432/postgres",
        supabase_service_role_key="test-service-role-key",
        cv_sources_bucket="cv-sources",
        cv_renderer_inputs_bucket="cv-renderer-inputs",
        cv_finals_bucket="cv-finals",
        cv_artifacts_bucket="cv-artifacts",
    )


def _write_valid_renderer(path: Path) -> None:
    path.write_bytes(DEFAULT_WHUB_RENDERER_PATH.read_bytes())


def _write_valid_assets(assets_dir: Path) -> None:
    assets_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("img_0dcab6df734b.png", "img_90df8f14aa40.png"):
        (assets_dir / filename).write_bytes((DEFAULT_WHUB_ASSETS_DIR / filename).read_bytes())


def _write_valid_fonts(fonts_dir: Path) -> None:
    fonts_dir.mkdir(parents=True, exist_ok=True)
    for weight in ("Regular", "Bold", "SemiBold", "Light"):
        filename = f"Poppins-{weight}.ttf"
        (fonts_dir / filename).write_bytes((DEFAULT_WHUB_FONTS_DIR / filename).read_bytes())


def test_startup_preflight_success_returns_safe_report(tmp_path: Path):
    renderer = tmp_path / "renderer.py"
    assets_dir = tmp_path / "assets"
    fonts_dir = tmp_path / "fonts"
    _write_valid_renderer(renderer)
    _write_valid_assets(assets_dir)
    _write_valid_fonts(fonts_dir)

    report = run_startup_preflight(_settings(tmp_path, renderer, assets_dir, fonts_dir))

    assert report == {
        "renderer": str(renderer),
        "assets_dir": str(assets_dir),
        "fonts_dir": str(fonts_dir),
        "fonts_source": "configured",
        "supabase": "configured",
    }
    assert "test-service-role-key" not in str(report)


def test_startup_preflight_fails_when_renderer_missing(tmp_path: Path):
    assets_dir = tmp_path / "assets"
    fonts_dir = tmp_path / "fonts"
    _write_valid_assets(assets_dir)
    _write_valid_fonts(fonts_dir)

    with pytest.raises(StartupPreflightError, match="Renderer W hub manquant"):
        run_startup_preflight(_settings(tmp_path, tmp_path / "missing.py", assets_dir, fonts_dir))


def test_startup_preflight_fails_when_external_renderer_diverges_from_repo_renderer(tmp_path: Path):
    renderer = tmp_path / "external_renderer.py"
    renderer.write_text("# legacy global renderer with divergent content\n", encoding="utf-8")
    assets_dir = tmp_path / "assets"
    fonts_dir = tmp_path / "fonts"
    _write_valid_assets(assets_dir)
    _write_valid_fonts(fonts_dir)

    with pytest.raises(StartupPreflightError) as exc_info:
        run_startup_preflight(_settings(tmp_path, renderer, assets_dir, fonts_dir))

    message = str(exc_info.value)
    assert "Renderer W hub divergent" in message
    assert str(renderer) in message
    assert str(DEFAULT_WHUB_RENDERER_PATH) in message
    assert "test-service-role-key" not in message


def test_startup_preflight_fails_when_asset_missing(tmp_path: Path):
    renderer = tmp_path / "renderer.py"
    fonts_dir = tmp_path / "fonts"
    _write_valid_renderer(renderer)
    _write_valid_fonts(fonts_dir)
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "img_0dcab6df734b.png").write_bytes((DEFAULT_WHUB_ASSETS_DIR / "img_0dcab6df734b.png").read_bytes())

    with pytest.raises(StartupPreflightError, match="Asset W hub manquant"):
        run_startup_preflight(_settings(tmp_path, renderer, assets_dir, fonts_dir))


def test_startup_preflight_fails_when_asset_dimensions_are_wrong(tmp_path: Path):
    renderer = tmp_path / "renderer.py"
    assets_dir = tmp_path / "assets"
    fonts_dir = tmp_path / "fonts"
    _write_valid_renderer(renderer)
    assets_dir.mkdir()
    Image.new("RGBA", (10, 10)).save(assets_dir / "img_0dcab6df734b.png")
    Image.new("RGBA", (1192, 1192)).save(assets_dir / "img_90df8f14aa40.png")
    _write_valid_fonts(fonts_dir)

    with pytest.raises(StartupPreflightError, match="Mauvais asset W hub"):
        run_startup_preflight(_settings(tmp_path, renderer, assets_dir, fonts_dir))


def test_startup_preflight_fails_when_asset_content_diverges_with_valid_dimensions(tmp_path: Path):
    renderer = tmp_path / "renderer.py"
    assets_dir = tmp_path / "assets"
    fonts_dir = tmp_path / "fonts"
    _write_valid_renderer(renderer)
    _write_valid_assets(assets_dir)
    _write_valid_fonts(fonts_dir)
    Image.new("RGBA", (1051, 398), (255, 0, 0, 255)).save(assets_dir / "img_0dcab6df734b.png")

    with pytest.raises(StartupPreflightError) as exc_info:
        run_startup_preflight(_settings(tmp_path, renderer, assets_dir, fonts_dir))

    message = str(exc_info.value)
    assert "Asset W hub divergent" in message
    assert "sha256=" in message
    assert "test-service-role-key" not in message


def test_startup_preflight_fails_when_poppins_font_content_is_fake(tmp_path: Path):
    renderer = tmp_path / "renderer.py"
    assets_dir = tmp_path / "assets"
    fonts_dir = tmp_path / "fonts"
    _write_valid_renderer(renderer)
    _write_valid_assets(assets_dir)
    _write_valid_fonts(fonts_dir)
    (fonts_dir / "Poppins-Regular.ttf").write_bytes(b"fake-font")

    with pytest.raises(StartupPreflightError) as exc_info:
        run_startup_preflight(_settings(tmp_path, renderer, assets_dir, fonts_dir))

    message = str(exc_info.value)
    assert "Font Poppins divergente" in message
    assert "sha256=" in message
    assert "test-service-role-key" not in message


def test_startup_preflight_fails_when_configured_poppins_dir_is_partial_instead_of_repo_fallback(tmp_path: Path):
    renderer = tmp_path / "renderer.py"
    assets_dir = tmp_path / "assets"
    fonts_dir = tmp_path / "fonts"
    _write_valid_renderer(renderer)
    _write_valid_assets(assets_dir)
    fonts_dir.mkdir()
    (fonts_dir / "Poppins-Regular.ttf").write_bytes(b"fake-font")

    with pytest.raises(StartupPreflightError) as exc_info:
        run_startup_preflight(_settings(tmp_path, renderer, assets_dir, fonts_dir))

    message = str(exc_info.value)
    assert "Font Poppins divergente" in message
    assert str(fonts_dir / "Poppins-Regular.ttf") in message
    assert "repo_fallback" not in message
    assert "test-service-role-key" not in message


def test_startup_preflight_fails_when_configured_poppins_dir_is_partial_even_if_repo_fonts_exist(tmp_path: Path):
    renderer = tmp_path / "renderer.py"
    assets_dir = tmp_path / "assets"
    fonts_dir = tmp_path / "partial-fonts"
    _write_valid_renderer(renderer)
    _write_valid_assets(assets_dir)
    fonts_dir.mkdir()
    (fonts_dir / "Poppins-Regular.ttf").write_bytes(b"fake-font")

    with pytest.raises(StartupPreflightError) as exc_info:
        run_startup_preflight(_settings(tmp_path, renderer, assets_dir, fonts_dir))

    message = str(exc_info.value)
    assert "Fonts Poppins manquantes" in message or "Font Poppins divergente" in message
    assert "repo_fallback" not in message
    assert "test-service-role-key" not in message


def test_settings_rewrites_legacy_global_renderer_path_to_repo_local_renderer(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    monkeypatch.setenv("WORKER_DB_URL", "postgresql://whub_worker:test@localhost:5432/postgres")
    monkeypatch.setenv("WHUB_RENDERER_PATH", str(LEGACY_WHUB_RENDERER_PATH))

    configured = Settings(
        supabase_url="https://example.supabase.co",
        supabase_anon_key="test-anon-key",
        worker_db_url="postgresql://whub_worker:***@localhost:5432/postgres",
    )

    assert configured.whub_renderer_path == str(DEFAULT_WHUB_RENDERER_PATH)


def test_settings_keeps_non_legacy_renderer_path_for_preflight_validation(tmp_path: Path, monkeypatch):
    external_renderer = tmp_path / "external_renderer.py"
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    monkeypatch.setenv("WORKER_DB_URL", "postgresql://whub_worker:test@localhost:5432/postgres")
    monkeypatch.setenv("WHUB_RENDERER_PATH", str(external_renderer))

    configured = Settings(
        supabase_url="https://example.supabase.co",
        supabase_anon_key="test-anon-key",
        worker_db_url="postgresql://whub_worker:***@localhost:5432/postgres",
    )

    assert configured.whub_renderer_path == str(external_renderer)


def test_settings_rewrites_legacy_tmp_poppins_path_to_repo_fonts(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    monkeypatch.setenv("WORKER_DB_URL", "postgresql://whub_worker:test@localhost:5432/postgres")
    monkeypatch.setenv("WHUB_FONTS_DIR", "/tmp/poppins_full")

    configured = Settings(
        supabase_url="https://example.supabase.co",
        supabase_anon_key="test-anon-key",
        worker_db_url="postgresql://whub_worker:***@localhost:5432/postgres",
    )

    assert configured.whub_fonts_dir == str(DEFAULT_WHUB_FONTS_DIR)


def test_main_runs_preflight_before_polling(monkeypatch):
    from src import main as worker_main

    calls: list[str] = []
    monkeypatch.setattr(
        worker_main,
        "run_startup_preflight",
        lambda: calls.append("preflight")
        or {
            "renderer": "/safe/renderer.py",
            "assets_dir": "/safe/assets",
            "fonts_dir": "/safe/fonts",
            "fonts_source": "configured",
            "supabase": "configured",
        },
    )

    def stop_after_first_poll():
        calls.append("claim")
        raise KeyboardInterrupt

    monkeypatch.setattr(worker_main, "claim_next_job", stop_after_first_poll)

    with pytest.raises(KeyboardInterrupt):
        worker_main.main()

    assert calls == ["preflight", "claim"]
