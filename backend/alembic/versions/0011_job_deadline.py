"""Fecha limite de la oferta.

JobPilot no tenia el concepto en ninguna parte: ni columna, ni extraccion, ni
aviso. Una oferta que cierra manana se veia igual que una que cierra en un mes,
y el barrido automatico seguia trayendolas despues de cerradas.

`validThrough` de schema.org la trae cuando la pagina la publica; cuando no,
job_importer._extract_deadline la busca en el texto, y solo detras de un
marcador explicito ("fecha limite", "application deadline"): adivinar un plazo
es peor que no tener ninguno.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-15 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS deadline DATE")
    # El barrido y la cola de swipe filtran por plazo vigente, y eso es un
    # recorrido por fecha sobre una tabla que crece ~20 filas cada 2 horas.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_deadline ON jobs (deadline) "
        "WHERE deadline IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jobs_deadline")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS deadline")
