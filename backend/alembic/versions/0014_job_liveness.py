"""jobs.closed_at y jobs.liveness_checked_at: ofertas que ya no existen.

Ver app/services/liveness.py. La idea viene de career-ops, que comprueba si
la oferta sigue viva antes de invertir tiempo en ella.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-21 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ")
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS liveness_checked_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS liveness_checked_at")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS closed_at")
