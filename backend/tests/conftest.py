import os

# Must run before ANY `from app...` import anywhere in the collected test
# tree — app.core.config.get_settings() is @lru_cache'd and reads
# DATABASE_URL at first call, so whichever module imports it first "locks
# in" the connection target for the whole test session. Pytest always
# imports the root conftest.py before collecting sibling test modules, so
# setting this here (before the sys.path manipulation below, which is the
# first thing that lets any test file `import app.*`) guarantees every
# router/integration test talks to the isolated test database, never the
# real jobflow one. See backend/README.md for the one-time `CREATE DATABASE
# jobflow_test` + schema-load setup this depends on.
# La contrasena sale del entorno, no escrita aqui: estaba fijada a "jobflow",
# que era el valor por defecto de docker-compose, asi que en cuanto la base de
# datos tuvo una contrasena de verdad la suite entera dejaba de conectar.
_PG_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "jobflow")
os.environ["DATABASE_URL"] = f"postgresql+asyncpg://jobflow:{_PG_PASSWORD}@db:5432/jobflow_test"

# Same reasoning as DATABASE_URL above, for the same @lru_cache'd settings
# object: cleared here, before anything imports app.core.config, so no test
# can reach the real Anthropic API.
#
# This is not only about determinism. Every AI service falls back to an
# offline path when the key is missing, so with a live key configured the
# suite silently switched paths: assertions about rule-based output started
# failing, runtime went from 60s to 286s, and — the part that matters — the
# test run spent real money on a metered key. A test that costs money to run
# is a test people stop running.
#
# A test that wants to exercise the AI path patches get_anthropic_client in
# the module under test (see test_anthropic_client.py), which is faster,
# free, and lets it assert on an exact response.
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["ANTHROPIC_WORKSPACE_ID"] = ""
# Same for the local model: with OLLAMA_BASE_URL set in the backend container
# the suite would call the real Ollama — slow, and the results would depend on
# whether the PC's model happens to be running.
os.environ["OLLAMA_BASE_URL"] = ""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.models.user import User

# Every app table that a router/integration test could write to, in an
# order that's irrelevant thanks to RESTART IDENTITY CASCADE below (CASCADE
# also clears dependent rows in tables not explicitly listed, e.g. a
# resume_version's own dependents, so this list only needs the tables
# tests actually insert into directly).
_TABLES_TO_CLEAN = [
    "applications",
    "job_matches",
    "resume_versions",
    "cover_letters",
    "device_tokens",
    "refresh_tokens",
    "system_heartbeats",
    "api_call_budgets",
    "error_logs",
    "external_job_cache",
    "jobs",
    "career_profiles",
    "users",
]


@pytest.fixture(scope="session", autouse=True)
def _require_test_database():
    """Hard safety rail: if this ever ran against the real `jobflow`
    database (e.g. someone removes/reorders the os.environ line above), the
    per-test TRUNCATE below would silently wipe production data. Fail loud
    and immediately instead."""
    db_name = engine.url.database
    if db_name != "jobflow_test":
        pytest.exit(
            f"Refusing to run integration tests against database '{db_name}' — "
            "expected 'jobflow_test'. Check conftest.py's DATABASE_URL override.",
            returncode=1,
        )


@pytest.fixture(autouse=True)
def _no_admin_reporting(monkeypatch):
    """Tests never report token usage to a real JobPilot Admin, even when the
    container's env has ADMIN_URL set. Tests that need it set it themselves."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ADMIN_URL", None)
    monkeypatch.setattr(settings, "ADMIN_INGEST_KEY", None)


@pytest_asyncio.fixture(autouse=True)
async def _clean_db():
    """Truncate after each test (not before) so a failed test's data stays
    inspectable via psql until the next test runs. Plain TRUNCATE rather
    than a transactional-rollback fixture — wiring a per-test outer
    transaction through FastAPI's own get_db-injected session is fiddly
    with AsyncSessionLocal's expire_on_commit=False config, and at this
    table/row count TRUNCATE is simple, reliable, and plenty fast.

    Also disposes the shared engine's connection pool afterward: pytest-
    asyncio (in this version, function-scoped by default) hands every test
    function a brand-new event loop, but app.db.session.engine is a single
    module-level singleton created once at import time — its pooled
    asyncpg connections stay bound to whichever loop first used them.
    Without disposing here, the *next* test's event loop tries to reuse a
    connection created under a now-closed loop and fails with "Future
    attached to a different loop". Disposing forces a fresh pool (and
    fresh connections, bound to the *next* test's loop) on next use."""
    yield
    async with AsyncSessionLocal() as session:
        for table in _TABLES_TO_CLEAN:
            await session.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))
        await session.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def async_client():
    """In-process HTTP client against the real FastAPI app — no server
    process, no network socket, so it's as fast as calling the route
    functions directly while still exercising the full request/response
    cycle (dependency injection, validation, exception handlers)."""
    transport = ASGITransport(app=app)
    base_url = f"http://test{settings.API_V1_PREFIX}"
    async with AsyncClient(transport=transport, base_url=base_url) as client:
        yield client


@pytest_asyncio.fixture
async def user_and_headers():
    """A ready-to-use, already-verified user + Bearer auth header. Inserts
    the row directly and mints the token via create_access_token rather
    than going through POST /auth/register, so router tests don't depend
    on auth.py's own correctness, the email-verification side effect, or
    trip /auth/register's 5/minute rate limit when many tests run in the
    same minute."""
    async with AsyncSessionLocal() as session:
        user = User(
            email="router-test@example.com",
            hashed_password=hash_password("Test1234!"),
            full_name="Router Test",
            email_verified=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    token = create_access_token(str(user.id))
    return user, {"Authorization": f"Bearer {token}"}
