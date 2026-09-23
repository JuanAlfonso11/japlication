"""Fuente web3career: API de Web3.career (token gratis).

Ver app/services/web3career.py.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-23 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD VALUE no puede ir dentro de una transaccion; igual que 0005 y 0013.
    op.execute("COMMIT")
    op.execute("ALTER TYPE job_source ADD VALUE IF NOT EXISTS 'web3career'")


def downgrade() -> None:
    # No existe ALTER TYPE ... DROP VALUE en PostgreSQL; ver 0005.
    pass
