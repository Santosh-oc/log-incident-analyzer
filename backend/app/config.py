"""Application settings loaded from environment / .env file."""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    max_log_size_mb: int = 50
    base_path: str = ""
    # When True (platform app behind the gateway) every request must carry the
    # X-Auth-Request-User header or it is rejected with 401. Off for local dev
    # and workspace tiles, which are already behind platform auth.
    require_auth: bool = False

    database_url: str = "postgresql+psycopg://log_analyzer:log_analyzer@localhost:5432/log_analyzer"

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        # The platform injects postgresql://... which SQLAlchemy maps to
        # psycopg2; we ship psycopg (v3), so pin the driver explicitly.
        for scheme in ("postgresql://", "postgres://"):
            if v.startswith(scheme):
                return v.replace(scheme, "postgresql+psycopg://", 1)
        return v

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket_logs: str = "logs"

    llm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = "qwen"
    llm_api_key: str = ""
    llm_timeout_seconds: float = 120
    llm_max_tokens: int = 1024

    incident_gap_minutes: int = 5
    max_incidents_per_analysis: int = 50


@lru_cache
def get_settings() -> Settings:
    return Settings()
