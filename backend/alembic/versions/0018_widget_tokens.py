"""Credenciales del widget de Android: decidir desde la pantalla de inicio.

Ver app/models/widget_token.py y app/api/v1/routers/widget.py.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-09 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS widget_tokens (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_id     TEXT NOT NULL,
            token_hash    TEXT UNIQUE NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_used_at  TIMESTAMPTZ,
            revoked_at    TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_widget_tokens_user ON widget_tokens (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_widget_tokens_device ON widget_tokens (device_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_widget_tokens_device")
    op.execute("DROP INDEX IF EXISTS idx_widget_tokens_user")
    op.execute("DROP TABLE IF EXISTS widget_tokens")
