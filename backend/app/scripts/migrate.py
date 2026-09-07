"""Brings the database schema up to date, then gets out of the way.

Run from the container entrypoint before uvicorn starts. Until this existed,
Alembic was configured but never actually executed: there was no
`alembic_version` table in either database, and every schema change had to be
applied by hand with an ALTER TABLE — twice, since the test database is
separate. Three columns went in that way, and the fourth was going to be the
one somebody forgot.

The wrinkle is that this project has *two* ways of creating a schema, and
they must not fight:

  * `db/schema.sql` is mounted into the Postgres image's
    docker-entrypoint-initdb.d, so a brand-new volume comes up already
    complete. Running migrations over that would try to CREATE TABLE on
    tables that exist.
  * `alembic/versions/` is the incremental history, and revision 0001 simply
    replays `db/schema.sql`.

So this looks at what's actually in front of it:

  1. `alembic_version` present -> a managed database: upgrade it.
  2. No `alembic_version` but the schema is there -> it was created from
     schema.sql (either by initdb or, for the pre-existing databases, by
     hand). It is already current, so stamp it and run nothing.
  3. Empty -> upgrade from zero; 0001 replays schema.sql and the rest follow.

This rests on the invariant the project already documents: `db/schema.sql`
is the source of truth and stays in sync with the migration history. Adding
a migration without updating schema.sql would leave case 2 stamping a
database that is missing that column.
"""

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

# Alembic's own config lives at the backend root, next to `alembic/`.
BACKEND_ROOT = Path(__file__).resolve().parents[2]

# The database is healthy per compose's healthcheck before this runs, but a
# few retries cost nothing and cover the gap on a cold `docker compose up`
# where Postgres is still finishing its own startup.
_CONNECT_ATTEMPTS = 10
_CONNECT_DELAY_SECONDS = 2


def _asyncpg_dsn() -> str:
    """asyncpg wants a plain postgresql:// DSN, not SQLAlchemy's
    dialect-qualified one. Used directly rather than through SQLAlchemy
    because these are two `to_regclass` probes, and because asyncpg is
    already a dependency while a sync driver is not — this shouldn't add
    psycopg2 to the image for the sake of a startup check."""
    from app.core.config import settings

    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def _inspect_async() -> tuple[bool, bool]:
    last_error: Exception | None = None
    for attempt in range(1, _CONNECT_ATTEMPTS + 1):
        try:
            conn = await asyncpg.connect(_asyncpg_dsn())
            break
        except Exception as exc:  # noqa: BLE001 - any connection failure is retryable here
            last_error = exc
            if attempt == _CONNECT_ATTEMPTS:
                raise
            print(
                f"[migrate] Base no disponible todavia (intento {attempt}/{_CONNECT_ATTEMPTS})…",
                flush=True,
            )
            await asyncio.sleep(_CONNECT_DELAY_SECONDS)
    else:  # pragma: no cover - the loop either breaks or raises
        raise RuntimeError(f"No se pudo conectar a la base: {last_error}")

    try:
        has_version = await conn.fetchval("SELECT to_regclass('public.alembic_version') IS NOT NULL")
        # `users` stands in for "the schema exists" — it's the first table
        # schema.sql creates and nothing else can plausibly create it.
        has_schema = await conn.fetchval("SELECT to_regclass('public.users') IS NOT NULL")
        return bool(has_version), bool(has_schema)
    finally:
        await conn.close()


def _inspect() -> tuple[bool, bool]:
    """Returns (alembic_version exists, schema already created)."""
    return asyncio.run(_inspect_async())


def _alembic(*args: str) -> None:
    result = subprocess.run(["alembic", *args], cwd=BACKEND_ROOT)
    if result.returncode != 0:
        raise SystemExit(
            f"alembic {' '.join(args)} failed with exit code {result.returncode}. "
            "Refusing to start the API against a schema in an unknown state."
        )


def _retarget_database(database: str) -> None:
    """Points this run at a different database on the same server.

    Exists for `jobflow_test`, which is a separate, persistent database the
    integration tests own (see backend/tests/conftest.py). It drifted out of
    sync exactly like the main one did, and had to be patched by hand too —
    so it needs a documented way to be migrated, not a second manual ALTER.

    Mutates DATABASE_URL in the environment rather than passing a flag,
    because the `alembic` subprocess below reads it through the app's own
    settings (see alembic/env.py) and would otherwise still target the
    default database.
    """
    from app.core.config import settings

    parts = urlsplit(settings.DATABASE_URL)
    retargeted = urlunsplit(parts._replace(path=f"/{database}"))
    os.environ["DATABASE_URL"] = retargeted
    # settings was already instantiated at import time, so update it too.
    settings.DATABASE_URL = retargeted
    print(f"[migrate] Apuntando a la base '{database}'.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lleva el esquema al dia.")
    parser.add_argument(
        "--database",
        help="Migrar otra base del mismo servidor (p. ej. jobflow_test) en vez de la configurada.",
    )
    args = parser.parse_args()

    if args.database:
        _retarget_database(args.database)

    has_version, has_schema = _inspect()

    if has_version:
        print("[migrate] Base gestionada por Alembic -> upgrade head", flush=True)
        _alembic("upgrade", "head")
    elif has_schema:
        print(
            "[migrate] Esquema creado desde db/schema.sql y sin historial -> stamp head",
            flush=True,
        )
        _alembic("stamp", "head")
    else:
        print("[migrate] Base vacia -> upgrade head desde cero", flush=True)
        _alembic("upgrade", "head")

    print("[migrate] Esquema al dia.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        # Starting the API against a half-migrated schema is worse than not
        # starting: it serves wrong data instead of failing where someone
        # will look.
        print(f"[migrate] ERROR: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
