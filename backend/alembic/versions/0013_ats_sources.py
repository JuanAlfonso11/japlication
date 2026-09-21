"""Fuentes greenhouse, lever y ashby: ofertas leidas del ATS de cada empresa.

Ver app/services/ats_boards.py. Cada oferta que entra por aqui trae el
formulario real (apply_url) desde el primer momento.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-21 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD VALUE no puede ir dentro de una transaccion en las versiones que
    # soportamos; igual que 0005 y 0007.
    op.execute("COMMIT")
    for value in ("greenhouse", "lever", "ashby"):
        op.execute(f"ALTER TYPE job_source ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # No existe ALTER TYPE ... DROP VALUE en PostgreSQL; ver 0005.
    pass
