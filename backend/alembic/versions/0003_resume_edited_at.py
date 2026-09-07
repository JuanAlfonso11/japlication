"""Add resume_versions.edited_at — marks a version the user corrected.

Generated resumes were read-only: there was no way to fix a bad bullet
before exporting the PDF. With editing, the edited text is worth more than
freshly generated wording, because it carries the user's own corrections —
so this timestamp also lets `_find_reusable_resume` prefer edited versions
when a later, similar posting looks for one to start from. That's how a
correction made once carries forward instead of being re-made every time.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-07 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "resume_versions",
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resume_versions", "edited_at")
