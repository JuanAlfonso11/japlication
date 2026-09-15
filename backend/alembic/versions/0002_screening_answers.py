"""Add career_profiles.screening_answers — the reusable answer bank.

Every application form asks the same handful of questions again (work
authorization, notice period, salary expectation, ...). Storing the answers
once on the profile is what lets the per-job application kit offer them
with a copy button instead of the user retyping them each time.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-07 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS, because revision 0001 does not carry a frozen snapshot of
    # the schema — it executes db/schema.sql as it stands today, and that file
    # already declares this column. Without the guard, `alembic upgrade head`
    # on an empty database dies here with DuplicateColumn, which is exactly
    # what scripts/check-schema-drift.ps1 caught.
    op.execute(
        "ALTER TABLE career_profiles "
        "ADD COLUMN IF NOT EXISTS screening_answers JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.drop_column("career_profiles", "screening_answers")
