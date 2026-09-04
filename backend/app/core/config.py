from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://jobflow:jobflow@localhost:5432/jobflow"

    # Auth. Access tokens are short-lived on purpose — they're a bearer
    # credential sent on every request, so a leaked one should go stale
    # fast. Staying logged in long-term comes from the refresh token
    # instead (a random opaque value, stored hashed in `refresh_tokens` so
    # it can be revoked — unlike a JWT, which is valid until it expires no
    # matter what). The frontend refreshes the access token transparently;
    # see lib/api.ts.
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 90

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

    # CORS. FRONTEND_ORIGIN is also used to build the email-verification link,
    # so it stays the single "canonical" origin. CORS_EXTRA_ORIGINS is a
    # comma-separated list of additional origins allowed to call the API —
    # e.g. a Tailscale hostname, so the same backend serves both the local
    # dev frontend and the Android app / phone browser over Tailscale.
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    CORS_EXTRA_ORIGINS: Optional[str] = None

    # This backend's own externally-reachable base URL (including API
    # prefix) — used to build the verification link's *first* hop, which
    # must hit GET /auth/verify-email on the backend itself (to validate the
    # token and flip email_verified) before it redirects on to
    # FRONTEND_ORIGIN. Same value as the frontend's NEXT_PUBLIC_API_URL.
    BACKEND_PUBLIC_URL: str = "http://localhost:8000/api/v1"

    # Push notifications (Firebase Cloud Messaging). Without this set, the
    # backend just skips sending pushes — same graceful-degradation pattern
    # as SMTP/Claude/every other optional external service.
    FIREBASE_CREDENTIALS_PATH: Optional[str] = None

    # App metadata
    PROJECT_NAME: str = "JobFlow AI"
    API_V1_PREFIX: str = "/api/v1"

    def cors_origins(self) -> list[str]:
        origins = [self.FRONTEND_ORIGIN]
        if self.CORS_EXTRA_ORIGINS:
            origins += [o.strip() for o in self.CORS_EXTRA_ORIGINS.split(",") if o.strip()]
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
