"""Bilingual profile: career_profiles.translations + resume_versions.language.

The base columns (headline/summary/experience) stay in ONE language and are
what the match engine reads, because TF-IDF compares words: mixing languages
in the text the matcher sees is what dropped the semantic score to ~1/100
when a Spanish profile met an English posting. So translations live beside
the base, never replacing it, and only surface when a CV is rendered.

`language` on resume_versions records which one a given CV was written in,
so the list of generated CVs can show it and a reused version is never
handed to a posting in the other language by accident.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-09 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "career_profiles",
        sa.Column(
            "translations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "resume_versions",
        sa.Column("language", sa.Text(), nullable=False, server_default=sa.text("'en'")),
    )


def downgrade() -> None:
    op.drop_column("resume_versions", "language")
    op.drop_column("career_profiles", "translations")
