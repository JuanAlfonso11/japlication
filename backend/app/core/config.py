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

    # Optional live job search (SerpApi's Google Jobs engine — https://serpapi.com/search?engine=google_jobs)
    SERPAPI_API_KEY: Optional[str] = None
    SERPAPI_DEFAULT_HL: str = "es"
    SERPAPI_DEFAULT_GL: str = "us"

    # Optional live job search — Upwork GraphQL API (OAuth2 authorization-code
    # flow; register an app at https://www.upwork.com/developer/apps to get
    # these). Unset by default: the "Upwork" search provider stays hidden
    # until configured.
    UPWORK_CLIENT_ID: Optional[str] = None
    UPWORK_CLIENT_SECRET: Optional[str] = None
    UPWORK_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/upwork/callback"

    # CORS
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # App metadata
    PROJECT_NAME: str = "JobFlow AI"
    API_V1_PREFIX: str = "/api/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
