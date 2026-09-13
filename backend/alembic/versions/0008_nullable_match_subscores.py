"""Let a match's technical/experience sub-scores be unknown.

"This posting lists no skills" used to be stored as technical_score = 100 —
a perfect score for a posting the engine knows nothing about. Measured on
this database: 17 of the 196 scored jobs had no parsed skills, every one of
them got technical 100 AND experience 100, and they were 17 of the 19 jobs
scoring 75+. NULL now means unknown, the way semantic_score already could
be, and compute_match leaves unknown components out of the average.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-13 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column in ("technical_score", "experience_score"):
        op.alter_column("job_matches", column, existing_type=sa.Numeric(5, 2), nullable=True)


def downgrade() -> None:
    # Unknown has no pre-0008 representation; 0 is the honest floor, since
    # the old NOT NULL columns could not say "we don't know".
    for column in ("technical_score", "experience_score"):
        op.execute(f"UPDATE job_matches SET {column} = 0 WHERE {column} IS NULL")
        op.alter_column("job_matches", column, existing_type=sa.Numeric(5, 2), nullable=False)
