"""Add 'workingnomads' and 'remoteok' to the job_source enum.

Two more free, no-key providers, verified live before integrating (see
docs/PUBLIC_APIS_RESEARCH.md). Remote OK was previously investigated and
set aside over a Cloudflare gate that turns out to be satisfied by the
browser User-Agent the project already sends.

ALTER TYPE ... ADD VALUE cannot run inside a transaction block on older
PostgreSQL, and Alembic wraps migrations in one — hence the explicit
COMMIT before each statement. IF NOT EXISTS makes the whole thing
re-runnable, which matters because both values were already applied by
hand to the live databases before this migration existed.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-07 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE job_source ADD VALUE IF NOT EXISTS 'workingnomads'")
    op.execute("COMMIT")
    op.execute("ALTER TYPE job_source ADD VALUE IF NOT EXISTS 'remoteok'")


def downgrade() -> None:
    # PostgreSQL has no ALTER TYPE ... DROP VALUE. Undoing this would mean
    # recreating the enum and rewriting every column that uses it, which is
    # far more destructive than leaving two unused labels in place.
    pass
