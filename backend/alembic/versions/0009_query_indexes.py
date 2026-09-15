"""Indexes for the queries the app actually runs.

The existing indexes cover the cases that were easy to see coming (GIN on
search_vector, trigram on company, the user_id+score composite). Three that
the real query shapes need were missing:

1. `jobs (created_at DESC)` — GET /jobs ends every listing with
   `ORDER BY jobs.created_at DESC`. With no index that is a full scan plus a
   sort of the whole table, including the `description` column, on every
   page load. The table grows by ~20 rows every 2 hours from the sweep.

2. `applications (job_id)` and `job_matches (job_id)` — both are foreign
   keys joined from the job side (_attach_match, the pipeline view), and
   neither had an index leading with job_id. `idx_job_matches_user_score` is
   (user_id, overall_score) — no help for a lookup by job_id. Unindexed FKs
   also make every DELETE on `jobs` scan both child tables.

Written as a migration rather than only in db/schema.sql on purpose: putting
it in schema.sql alone is exactly the drift that made migration 0006/0007
invisible to freshly-created databases. Both files, always, together — see
scripts/check-schema-drift.ps1.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-15 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_applications_job ON applications (job_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_job_matches_job ON job_matches (job_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_job_matches_job")
    op.execute("DROP INDEX IF EXISTS idx_applications_job")
    op.execute("DROP INDEX IF EXISTS idx_jobs_created_at")
