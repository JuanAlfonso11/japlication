"""Fuente tecnoempleo: RSS publico de Tecnoempleo (Espana).

La fuente se quito despues (solo empleo en Espana, nada remoto abierto a
LatAm). El valor queda en el ENUM porque Postgres no permite quitarlo sin
recrear el tipo; ningun codigo lo escribe. Mismo caso que francetravail.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-23 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD VALUE no puede ir dentro de una transaccion; igual que 0005 y 0013.
    op.execute("COMMIT")
    op.execute("ALTER TYPE job_source ADD VALUE IF NOT EXISTS 'tecnoempleo'")


def downgrade() -> None:
    # No existe ALTER TYPE ... DROP VALUE en PostgreSQL; ver 0005.
    pass
