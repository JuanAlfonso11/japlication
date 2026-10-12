"""Borradores del agente de aplicacion.

Ver app/models/application_draft.py, app/services/apply_agent/ y
tasks/agente-aplicacion.md.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-12 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS application_drafts (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            application_id  UUID NOT NULL UNIQUE REFERENCES applications(id) ON DELETE CASCADE,
            ats             TEXT NOT NULL,
            form_url        TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'ready' CHECK (status IN (
                'ready', 'needs_user', 'failed', 'approved', 'scheduled', 'submitted', 'cancelled'
            )),
            auto_eligible   BOOLEAN NOT NULL DEFAULT false,
            content         JSONB NOT NULL DEFAULT '{}'::jsonb,
            error           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_application_drafts_user ON application_drafts (user_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_application_drafts_user")
    op.execute("DROP TABLE IF EXISTS application_drafts")
