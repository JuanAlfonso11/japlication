"""Convenience helper to apply db/schema.sql directly against the configured database.

This is an alternative to running Alembic migrations, useful for quick local setup:

    python -m app.db.init_db

It reads the repository-level `db/schema.sql` (the single source of truth for the
schema) and executes it against DATABASE_URL. It is idempotent-ish in that the
underlying schema.sql uses `CREATE TABLE`/`CREATE TYPE` without `IF NOT EXISTS` for
most objects, so it is intended for first-time setup of an empty database (mirrors
what the initial Alembic migration does).
"""

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

# backend/app/db/init_db.py -> repo_root/db/schema.sql
SCHEMA_SQL_PATH = Path(__file__).resolve().parents[3] / "db" / "schema.sql"


async def apply_schema() -> None:
    if not SCHEMA_SQL_PATH.exists():
        raise FileNotFoundError(f"schema.sql not found at {SCHEMA_SQL_PATH}")

    sql = SCHEMA_SQL_PATH.read_text()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            # asyncpg driver does not support multiple statements in one execute();
            # run the raw DDL through the underlying driver connection instead.
            raw_conn = await conn.get_raw_connection()
            await raw_conn.driver_connection.execute(sql)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(apply_schema())
    print(f"Applied schema from {SCHEMA_SQL_PATH}")


if __name__ == "__main__":
    main()
