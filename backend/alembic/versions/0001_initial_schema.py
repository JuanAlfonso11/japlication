"""Initial schema — mirrors db/schema.sql (the authoritative source of truth).

This migration reads the repository-level db/schema.sql and replays its
statements one at a time (split on top-level semicolons, respecting `$$`
dollar-quoted function bodies), so the database schema can never drift from
that file. Statements are executed individually rather than as one blob
because the asyncpg SQLAlchemy dialect's DBAPI cursor uses PostgreSQL's
extended query protocol (prepare + execute), which does not allow multiple
commands in a single prepared statement.

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# backend/alembic/versions/0001_initial_schema.py -> repo_root/db/schema.sql
SCHEMA_SQL_PATH = Path(__file__).resolve().parents[3] / "db" / "schema.sql"


def _split_sql_statements(sql: str) -> list[str]:
    """Split a SQL script into individual statements on top-level semicolons,
    treating `$$ ... $$` dollar-quoted bodies (used by plpgsql functions) as
    opaque so semicolons inside them aren't treated as statement boundaries,
    and stripping `--` line comments first (a semicolon *inside* a comment
    must not be treated as a statement boundary either)."""
    statements: list[str] = []
    buf: list[str] = []
    in_dollar_quote = False
    i = 0
    n = len(sql)
    while i < n:
        chunk = sql[i : i + 2]
        if not in_dollar_quote and chunk == "--":
            # Skip a line comment entirely (up to, but not including, the newline).
            newline_idx = sql.find("\n", i)
            i = n if newline_idx == -1 else newline_idx
            continue
        if chunk == "$$":
            in_dollar_quote = not in_dollar_quote
            buf.append(chunk)
            i += 2
            continue
        ch = sql[i]
        if ch == ";" and not in_dollar_quote:
            statements.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return [s for s in statements if s]


def upgrade() -> None:
    # db/schema.sql creates the `citext` extension *after* the `users` table
    # already declares an `email CITEXT` column (its own comment above that
    # line even flags this as a known gap: "citext extension needed ... /
    # fallback to text+lower index if unavailable"). Applying the file
    # statement-by-statement against a fresh database therefore fails before
    # ever reaching that line. Create it first (idempotent - the file's own
    # later `CREATE EXTENSION IF NOT EXISTS citext` becomes a harmless no-op)
    # so the migration faithfully produces the schema schema.sql *intends*
    # without editing that file.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    sql = SCHEMA_SQL_PATH.read_text()
    for statement in _split_sql_statements(sql):
        op.execute(statement)


def downgrade() -> None:
    for statement in [
        "DROP TABLE IF EXISTS cover_letters CASCADE",
        "DROP TABLE IF EXISTS resume_versions CASCADE",
        "DROP TABLE IF EXISTS applications CASCADE",
        "DROP TABLE IF EXISTS job_matches CASCADE",
        "DROP TABLE IF EXISTS jobs CASCADE",
        "DROP TABLE IF EXISTS career_profiles CASCADE",
        "DROP TABLE IF EXISTS users CASCADE",
        "DROP FUNCTION IF EXISTS set_updated_at CASCADE",
        "DROP TYPE IF EXISTS generation_source",
        "DROP TYPE IF EXISTS swipe_decision",
        "DROP TYPE IF EXISTS application_status",
        "DROP TYPE IF EXISTS job_source",
    ]:
        op.execute(statement)
