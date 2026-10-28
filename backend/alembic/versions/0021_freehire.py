"""Fuente freehire: el agregador de IT de la skill /freehire, sin clave.

Ver app/services/freehire.py.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-27 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD VALUE no puede ir dentro de una transaccion; igual que 0017.
    op.execute("COMMIT")
    op.execute("ALTER TYPE job_source ADD VALUE IF NOT EXISTS 'freehire'")


def downgrade() -> None:
    # No existe ALTER TYPE ... DROP VALUE en PostgreSQL; ver 0005.
    pass
