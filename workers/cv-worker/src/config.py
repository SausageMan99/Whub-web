from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings


WORKER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WHUB_RENDERER_PATH = WORKER_ROOT / "renderer" / "whub_cv_renderer.py"
LEGACY_WHUB_RENDERER_PATH = Path("/root/.hermes/scripts/whub_cv_renderer.py")
DEFAULT_WHUB_ASSETS_DIR = WORKER_ROOT / "assets" / "whub"
DEFAULT_WHUB_FONTS_DIR = WORKER_ROOT / "assets" / "fonts" / "poppins"


class Settings(BaseSettings):
    # ── Supabase / Database ────────────────────────────────────────────
    supabase_url: str
    # Public anon key used only for Supabase Storage REST operations.
    # Database access is always through worker_db_url / whub_worker.
    supabase_anon_key: str = ""
    # worker_database_url replaces supabase_service_role_key for the worker.
    # Format: postgresql://whub_worker:***@db.xxx.supabase.co:6543/postgres?pgbouncer=true
    worker_database_url: str = Field(default="", validation_alias="WORKER_DATABASE_URL")
    # Legacy env/constructor name accepted during transition only.
    worker_db_url: str = Field(default="", validation_alias="WORKER_DB_URL")
    # Kept for backward compatibility during transition; the worker no
    # longer uses this.  Set to empty string to disable.
    supabase_service_role_key: str = ""

    @model_validator(mode="after")
    def populate_worker_database_url_from_legacy_alias(self) -> "Settings":
        if not self.worker_database_url and self.worker_db_url:
            self.worker_database_url = self.worker_db_url
        elif self.worker_database_url and not self.worker_db_url:
            self.worker_db_url = self.worker_database_url
        return self

    # ── Worker identity ────────────────────────────────────────────────
    worker_name: str = "whub-cv-worker-01"
    poll_interval_seconds: int = 10
    max_attempts: int = 3

    # ── Storage buckets ────────────────────────────────────────────────
    cv_sources_bucket: str = "cv-sources"
    cv_renderer_inputs_bucket: str = "cv-renderer-inputs"
    cv_finals_bucket: str = "cv-finals"
    cv_artifacts_bucket: str = "cv-artifacts"

    # ── Hermes AI ──────────────────────────────────────────────────────
    hermes_cli_path: str = "hermes"
    hermes_profile: str = "default"
    whub_primary_model: str = "gpt-5.5"
    whub_primary_provider: str = "openai-codex"
    # 2025-06-05: fallback supprimé — MiniMax M3 est le seul modèle de structuration

    # ── Rendering assets ───────────────────────────────────────────────
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
        populate_by_name = True


settings = Settings()
