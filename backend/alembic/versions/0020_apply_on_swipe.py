"""Aplicar al deslizar: modo del usuario y el ciclo de envio del borrador.

  * users.apply_mode: que hace un swipe a la derecha.
      save   -- solo guardar (como antes)
      review -- preparar la aplicacion y esperar a que el usuario la apruebe
      auto   -- preparar y, si no falta nada, enviarla tras la ventana de
                deshacer (APPLY_UNDO_MINUTES), con tope diario
  * application_drafts: canal (greenhouse | email | external), cuando sale
    (scheduled_for), cuando salio (submitted_at), el CV y la carta que lleva,
    y los estados nuevos del ciclo (preparing, submitting, handoff).

Ver app/services/apply_agent/pipeline.py y tasks/agente-aplicacion.md.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-27 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS apply_mode TEXT NOT NULL DEFAULT 'review'
                CONSTRAINT users_apply_mode_check CHECK (apply_mode IN ('save', 'review', 'auto'))
        """
    )
    op.execute("ALTER TABLE application_drafts DROP CONSTRAINT IF EXISTS application_drafts_status_check")
    op.execute(
        """
        ALTER TABLE application_drafts
            ADD CONSTRAINT application_drafts_status_check CHECK (status IN (
                'preparing', 'ready', 'needs_user', 'failed', 'approved', 'scheduled',
                'submitting', 'submitted', 'handoff', 'cancelled'
            ))
        """
    )
    op.execute(
        """
        ALTER TABLE application_drafts
            ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'greenhouse'
                CONSTRAINT application_drafts_channel_check CHECK (channel IN ('greenhouse', 'email', 'external')),
            ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS resume_version_id UUID REFERENCES resume_versions(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS cover_letter_id UUID REFERENCES cover_letters(id) ON DELETE SET NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_application_drafts_scheduled "
        "ON application_drafts (scheduled_for) WHERE status = 'scheduled'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_application_drafts_scheduled")
    op.execute(
        """
        ALTER TABLE application_drafts
            DROP COLUMN IF EXISTS cover_letter_id,
            DROP COLUMN IF EXISTS resume_version_id,
            DROP COLUMN IF EXISTS submitted_at,
            DROP COLUMN IF EXISTS scheduled_for,
            DROP COLUMN IF EXISTS channel
        """
    )
    op.execute("ALTER TABLE application_drafts DROP CONSTRAINT IF EXISTS application_drafts_status_check")
    op.execute(
        """
        ALTER TABLE application_drafts
            ADD CONSTRAINT application_drafts_status_check CHECK (status IN (
                'ready', 'needs_user', 'failed', 'approved', 'scheduled', 'submitted', 'cancelled'
            ))
        """
    )
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS apply_mode")
