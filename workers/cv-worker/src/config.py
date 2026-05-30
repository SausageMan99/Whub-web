from pathlib import Path

from pydantic_settings import BaseSettings


WORKER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WHUB_RENDERER_PATH = WORKER_ROOT / "renderer" / "whub_cv_renderer.py"

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
    whub_assets_dir: str = "/root/.hermes/image_cache"
    whub_fonts_dir: str = "/tmp/poppins_full"
    tmp_dir: str = "/tmp/whub-cv-factory"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
