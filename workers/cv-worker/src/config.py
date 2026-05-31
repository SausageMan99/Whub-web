from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


WORKER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WHUB_RENDERER_PATH = WORKER_ROOT / "renderer" / "whub_cv_renderer.py"
LEGACY_WHUB_RENDERER_PATH = Path("/root/.hermes/scripts/whub_cv_renderer.py")
DEFAULT_WHUB_ASSETS_DIR = WORKER_ROOT / "assets" / "whub"
DEFAULT_WHUB_FONTS_DIR = WORKER_ROOT / "assets" / "fonts" / "poppins"

class Settings(BaseSettings):
    supabase_url: str
    supabase_service_role_key: str
    worker_name: str = "whub-cv-worker-01"
    poll_interval_seconds: int = 10
    max_attempts: int = 3
    cv_sources_bucket: str = "cv-sources"
    cv_renderer_inputs_bucket: str = "cv-renderer-inputs"
    cv_finals_bucket: str = "cv-finals"
    cv_artifacts_bucket: str = "cv-artifacts"
    hermes_cli_path: str = "hermes"
    hermes_profile: str = "default"
    whub_renderer_path: str = str(DEFAULT_WHUB_RENDERER_PATH)
    whub_assets_dir: str = str(DEFAULT_WHUB_ASSETS_DIR)
    whub_fonts_dir: str = str(DEFAULT_WHUB_FONTS_DIR)
    tmp_dir: str = "/tmp/whub-cv-factory"
    log_level: str = "INFO"

    @field_validator("whub_renderer_path", mode="before")
    @classmethod
    def use_packaged_renderer_for_legacy_global_path(cls, value: str) -> str:
        if value == str(LEGACY_WHUB_RENDERER_PATH):
            return str(DEFAULT_WHUB_RENDERER_PATH)
        return value

    @field_validator("whub_assets_dir", mode="before")
    @classmethod
    def use_packaged_assets_for_legacy_default(cls, value: str) -> str:
        if value == "/root/.hermes/image_cache":
            return str(DEFAULT_WHUB_ASSETS_DIR)
        return value

    @field_validator("whub_fonts_dir", mode="before")
    @classmethod
    def use_packaged_fonts_for_legacy_global_path(cls, value: str) -> str:
        if value == "/tmp/poppins_full":
            return str(DEFAULT_WHUB_FONTS_DIR)
        return value

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
