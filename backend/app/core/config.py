from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://jobflow:jobflow@localhost:5432/jobflow"

    # Auth
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 10080  # 7 days

    # Optional AI features
    ANTHROPIC_API_KEY: Optional[str] = None

    # Email (account verification). Without these set, the backend logs the
    # verification link instead of sending a real email — the app stays
    # fully usable in local dev without an SMTP account.
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "no-reply@jobflow.ai"
    SMTP_USE_TLS: bool = True

    # CV upload (PDF -> CareerProfile draft)
    MAX_CV_UPLOAD_MB: int = 8

    # CORS
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # App metadata
    PROJECT_NAME: str = "JobFlow AI"
    API_V1_PREFIX: str = "/api/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
