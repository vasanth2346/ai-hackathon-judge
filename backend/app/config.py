from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://judge:change-this-local-password@localhost:5432/hackathon_judge"
    redis_url: str = "redis://localhost:6379/0"
    frontend_origin: str = "http://localhost:3000"
    evidence_dir: Path = Path("./evidence")
    judge_encryption_key: str = ""
    llm_provider: str = "none"
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    llm_api_key: str = ""
    llm_model: str = "gemini-3.8-flash"
    auth_secret_key: str = ""
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    host_login_1_email: str = ""
    host_login_1_password: str = ""
    host_login_2_email: str = ""
    host_login_2_password: str = ""
    judge_stale_after_seconds: int = 900

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.evidence_dir.mkdir(parents=True, exist_ok=True)
    return settings
