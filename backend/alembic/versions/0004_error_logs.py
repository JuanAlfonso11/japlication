"""Add error_logs — one queryable place for everything that fails.

Backend errors used to live only in Docker's stdout (ephemeral, and you have
to know to go looking), and frontend errors on the phone existed nowhere at
all. This table is the single place to look when something breaks.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-07 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "error_logs",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False, server_default="error"),
        sa.Column("kind", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("stack", sa.Text(), nullable=True),
        sa.Column("method", sa.Text(), nullable=True),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_error_logs_created_at", "error_logs", [sa.text("created_at DESC")])
    op.create_index("idx_error_logs_request_id", "error_logs", ["request_id"])


def downgrade() -> None:
    op.drop_index("idx_error_logs_request_id", table_name="error_logs")
    op.drop_index("idx_error_logs_created_at", table_name="error_logs")
    op.drop_table("error_logs")
