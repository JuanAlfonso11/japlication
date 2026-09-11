"""Add 'linkedin' to the job_source enum — LinkedIn search through Bright Data.

Same shape as 0005: ALTER TYPE ... ADD VALUE cannot run inside a transaction
block on older PostgreSQL and Alembic wraps migrations in one, hence the
COMMIT first; IF NOT EXISTS keeps it re-runnable.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-11 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE job_source ADD VALUE IF NOT EXISTS 'linkedin'")


def downgrade() -> None:
    # No ALTER TYPE ... DROP VALUE in PostgreSQL; see 0005.
    pass
