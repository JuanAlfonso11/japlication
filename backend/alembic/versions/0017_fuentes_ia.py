"""Fuentes aidevboard y aijobs: bolsas de AI/ML sin clave.

Ver app/services/aidevboard.py y app/services/aijobs.py.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-08 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD VALUE no puede ir dentro de una transaccion; igual que 0005, 0013 y 0016.
    op.execute("COMMIT")
    op.execute("ALTER TYPE job_source ADD VALUE IF NOT EXISTS 'aidevboard'")
    op.execute("ALTER TYPE job_source ADD VALUE IF NOT EXISTS 'aijobs'")


def downgrade() -> None:
    # No existe ALTER TYPE ... DROP VALUE en PostgreSQL; ver 0005.
    pass
