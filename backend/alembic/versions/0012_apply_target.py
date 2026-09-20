"""Donde se postula de verdad a cada vacante.

Medido sobre las 252 vacantes guardadas: ninguna source_url apunta al
formulario. Todas apuntan al listado del portal (remotejobs.org, jobicy,
himalayas, linkedin) y el formulario esta un salto mas alla, en el ATS de la
empresa. Eso era un clic a ciegas por vacante, 252 veces.

Ver app/services/apply_target.py, que ademas deja escrito por que enviar la
candidatura automaticamente no es posible: los endpoints de envio de
Greenhouse y Lever existen pero exigen la clave de API del EMPLEADOR.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-20 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    ("apply_url", "TEXT"),
    ("apply_ats", "TEXT"),
    ("apply_email", "TEXT"),
    ("apply_note", "TEXT"),
    ("apply_checked_at", "TIMESTAMPTZ"),
)


def upgrade() -> None:
    for name, tipo in _COLUMNS:
        op.execute(f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {name} {tipo}")
    # El resolver recorre las que aun no se han mirado; sin indice eso es un
    # recorrido completo de la tabla cada vez que corre.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_apply_unchecked ON jobs (created_at) "
        "WHERE apply_checked_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jobs_apply_unchecked")
    for name, _tipo in _COLUMNS:
        op.execute(f"ALTER TABLE jobs DROP COLUMN IF EXISTS {name}")
