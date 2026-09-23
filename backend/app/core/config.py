import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Secrets that must never reach a running deployment. The old default
# ("dev-secret-change-me") is committed in this repo and in
# docker-compose.yml, so anyone who reads the source can forge an access
# token for any user. Booting with one of these is not a warning-level
# problem — it is an unauthenticated-admin problem that looks completely
# healthy from the outside, which is why _validate_secrets() below refuses
# to start instead of logging and continuing.
_PLACEHOLDER_JWT_SECRETS = frozenset(
    {
        "dev-secret-change-me",
        "change-me-in-.env",
        "change-me",
        "changeme",
        "secret",
        "supersecret",
        "your-secret-key",
    }
)
_MIN_JWT_SECRET_LENGTH = 32

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
    #: The model every AI feature uses. Was declared as a module constant in
    #: all seven services, which is exactly the duplication anthropic_client
    #: was created to remove — the model string just escaped it. Changing it
    #: in six places and missing the seventh fails silently: that feature
    #: keeps calling the old model and nothing complains.
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    #: Stop-the-bleeding ceiling on Anthropic calls per UTC day. Anthropic is
    #: the only API here that bills rather than running out of a free quota,
    #: and every caller falls back to an offline path on failure — so a
    #: runaway loop would spend money with no visible symptom at all. Set far
    #: above normal use (a sweep scores ~20 jobs every 2 hours); it exists to
    #: catch a bug, not to throttle the feature. Also set a real spend limit
    #: in the Anthropic console: this counter resets on container restart.
    ANTHROPIC_DAILY_CALL_BUDGET: int = 250

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

    #: Per-request timeout for the 15 external job providers. Was a literal
    #: `timeout=20.0` repeated in every connector — which also meant each one
    #: could hold a connection 8 seconds past the aggregate's own 12s deadline,
    #: long after nobody was waiting for it. Kept just under that deadline so a
    #: straggler is abandoned rather than orphaned. See
    #: services/external_jobs/http.py.
    EXTERNAL_JOBS_TIMEOUT_SECONDS: float = 11.0

    #: How long a normalized search result stays importable without a new
    #: search. Hours, not days, on purpose: this covers the gap between
    #: seeing a result and pressing "Agregar a la cola" — across a restart, a
    #: lunch break, overnight — not a private index of the job market. A
    #: week-old posting is likely filled, and importing it would put a dead
    #: listing in the swipe queue, which is worse than asking for a new search.
    EXTERNAL_JOBS_CACHE_TTL_HOURS: int = 48

    #: Greenhouse/Lever/Ashby publican TODO lo de cada empresa, incluidas
    #: plazas presenciales en oficinas lejanas. Por defecto solo remotas; un
    #: filtro explicito de modalidad en la busqueda manda sobre esto.
    ATS_REMOTE_ONLY: bool = True

    #: Registro abierto: quien descarga el APK se crea su cuenta sin VPN. Los
    #: topes diarios de api_budget (Anthropic, Adzuna, SerpApi) son globales y
    #: siguen protegiendo la factura. Ponlo a 0 en .env para cerrar el registro
    #: despues de la primera cuenta.
    ALLOW_EXTRA_REGISTRATIONS: bool = True

    # /docs, /redoc and /openapi.json. Off by default: the app is public and
    # the full API map helps nobody but an attacker. ENABLE_API_DOCS=1 in
    # .env brings them back while developing.
    ENABLE_API_DOCS: bool = False

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


def _running_under_pytest() -> bool:
    # conftest.py imports pytest long before it imports app.core.config, so
    # by the time this runs in a test session pytest is already in
    # sys.modules. Checked this way (rather than via PYTEST_CURRENT_TEST,
    # which is only set once a test *starts*) because validation happens at
    # import time, during collection.
    return "pytest" in sys.modules


def _validate_secrets(settings: Settings) -> None:
    """Refuse to boot with a guessable JWT_SECRET.

    A weak secret here means anyone who can read this repository can mint a
    valid access token for any account. There is no degraded mode worth
    offering for that, so this raises instead of warning — the container
    failing to start is a loud, obvious problem, whereas a forged-token
    backend looks perfectly healthy while it is wide open.

    Skipped under pytest (the suite never sets JWT_SECRET and does not need
    to) and behind ALLOW_INSECURE_JWT_SECRET=1 for throwaway local runs.
    """
    if _running_under_pytest() or os.getenv("ALLOW_INSECURE_JWT_SECRET") == "1":
        return

    value = (settings.JWT_SECRET or "").strip()
    problem: Optional[str] = None
    if not value:
        problem = "is empty"
    elif value.lower() in _PLACEHOLDER_JWT_SECRETS:
        problem = "is still the placeholder value shipped with the repo"
    elif len(value) < _MIN_JWT_SECRET_LENGTH:
        problem = f"is only {len(value)} characters (minimum {_MIN_JWT_SECRET_LENGTH})"

    if problem:
        raise RuntimeError(
            f"JWT_SECRET {problem}. Anyone who can read this repo could forge an "
            "access token for any account, so the backend will not start.\n"
            "Generate one with:  python -c \"import secrets; print(secrets.token_urlsafe(48))\"\n"
            "then set JWT_SECRET in .env and restart.\n"
            "(For a throwaway local run only: ALLOW_INSECURE_JWT_SECRET=1)"
        )


def redact_secret(value: Optional[str]) -> str:
    """Render a secret safe to put in a log line or an error payload.

    Never returns the value itself. Keeps just enough shape to tell "the key
    is configured" from "the key is missing" and to distinguish two keys
    from each other while debugging — which is the only reason to print
    anything about a credential at all.
    """
    if not value:
        return "<unset>"
    return f"<set:{len(value)} chars, ends …{value[-4:]}>"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.SYSTEM_HEARTBEAT_SECRET:
        settings.SYSTEM_HEARTBEAT_SECRET = _load_or_create_heartbeat_secret()
    _validate_secrets(settings)
    return settings


settings = get_settings()
