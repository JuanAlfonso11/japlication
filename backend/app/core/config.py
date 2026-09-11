import secrets
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Persisted across container restarts via the bind-mounted ./backend/runtime
# volume (see docker-compose.yml) — so an auto-generated heartbeat secret
# survives `docker compose restart backend` instead of invalidating every
# scheduled script's next call.
_HEARTBEAT_SECRET_FILE = Path("/app/runtime/heartbeat_secret")


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
    #: Only needed when the key is NOT itself scoped to a workspace — those
    #: keys are rejected with a 400 unless every request carries the
    #: anthropic-workspace-id header. Sent whenever it is set; see
    #: services/anthropic_client.py.
    ANTHROPIC_WORKSPACE_ID: Optional[str] = None

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

    # Adzuna (job search aggregator, ~12 countries). Free self-serve key at
    # https://developer.adzuna.com/ — both must be set or the provider is
    # skipped, same graceful-degradation pattern as above.
    ADZUNA_APP_ID: Optional[str] = None
    ADZUNA_APP_KEY: Optional[str] = None

    # USAJobs (official US federal government jobs). Free self-serve key at
    # https://developer.usajobs.gov/ — USAJOBS_USER_AGENT is the email
    # address registered with the key (USAJobs requires it as a request
    # header alongside the key itself).
    USAJOBS_API_KEY: Optional[str] = None
    USAJOBS_USER_AGENT: Optional[str] = None

    # SerpApi (Google Jobs — aggregates LinkedIn/Indeed/Glassdoor/
    # ZipRecruiter/etc. via Google's own public job-posting index, never
    # touching linkedin.com directly). Free self-serve key at
    # https://serpapi.com/users/sign_up.
    SERPAPI_API_KEY: Optional[str] = None

    # Where LinkedIn searches when Discover sends no location. LinkedIn needs
    # one, and for remote postings it decides which count as open to you.
    LINKEDIN_LOCATION: str = "Worldwide"

    # Android in-app update check (GET /app/android-update) — lets the app
    # prompt "there's a newer build" without a cable. Bump
    # ANDROID_LATEST_VERSION_CODE to match android/app/build.gradle's
    # versionCode and point ANDROID_UPDATE_APK_URL at wherever the new APK
    # is being served (see scripts/apk-server/) every time a native build
    # ships. Unset (None) means no update is tracked — the banner just
    # never shows, same graceful-degradation pattern as everywhere else.
    ANDROID_LATEST_VERSION_CODE: Optional[int] = None
    ANDROID_LATEST_VERSION_NAME: Optional[str] = None
    ANDROID_UPDATE_APK_URL: Optional[str] = None
    ANDROID_UPDATE_NOTES: Optional[str] = None

    # Shared secret the scheduled scripts (scripts/*.ps1, all running on
    # this same machine) send when POSTing to /system/heartbeat. If unset
    # here, get_settings() below auto-generates one and persists it to
    # _HEARTBEAT_SECRET_FILE so every caller — including the standalone
    # PowerShell scripts, which read that same file — agrees on it without
    # requiring manual setup, and the endpoint is never left accepting
    # unauthenticated callers by default.
    SYSTEM_HEARTBEAT_SECRET: Optional[str] = None

    # App metadata
    PROJECT_NAME: str = "JobFlow AI"
    API_V1_PREFIX: str = "/api/v1"

    def cors_origins(self) -> list[str]:
        origins = [self.FRONTEND_ORIGIN]
        if self.CORS_EXTRA_ORIGINS:
            origins += [o.strip() for o in self.CORS_EXTRA_ORIGINS.split(",") if o.strip()]
        return origins


def _load_or_create_heartbeat_secret() -> str:
    try:
        if _HEARTBEAT_SECRET_FILE.exists():
            existing = _HEARTBEAT_SECRET_FILE.read_text().strip()
            if existing:
                return existing
        generated = secrets.token_urlsafe(32)
        _HEARTBEAT_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        _HEARTBEAT_SECRET_FILE.write_text(generated)
        return generated
    except OSError:
        # No writable /app/runtime mount (e.g. running outside the compose
        # setup, such as in tests) — fall back to a per-process secret so
        # the endpoint still requires one, it just won't survive a restart.
        return secrets.token_urlsafe(32)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.SYSTEM_HEARTBEAT_SECRET:
        settings.SYSTEM_HEARTBEAT_SECRET = _load_or_create_heartbeat_secret()
    return settings


settings = get_settings()
