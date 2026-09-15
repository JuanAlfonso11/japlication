"""Durable copy of external search results, so importing one survives a restart.

Each connector cached its normalized results in a module-level dict with a
15-minute TTL, and POST /jobs/search/import read from it. Every restart
emptied all fifteen — the watchdog recovering a container, a rebuild,
shipping an APK — and the user, holding a list of results on screen, got
"this search result has expired" for a posting they were looking at.

See app/services/external_jobs/result_cache.py. The dicts stay as the fast
path; this table is the fallback that outlives the process.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-15 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS external_job_cache (
            source       TEXT NOT NULL,
            external_id  TEXT NOT NULL,
            payload      JSONB NOT NULL,
            cached_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (source, external_id)
        )
        """
    )
    # The sweep deletes by age across every provider, so it leads with the
    # timestamp; the lookup by (source, external_id) is the primary key.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_external_job_cache_cached_at "
        "ON external_job_cache (cached_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_external_job_cache_cached_at")
    op.execute("DROP TABLE IF EXISTS external_job_cache")
