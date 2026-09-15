"""Runs the same auto-import sweep GET /jobs/search/auto-import does, for
every user, without needing the app open. Meant to run unattended on a
schedule (see scripts/daily-job-sweep.ps1 +
scripts/install-job-sweep-schedule.ps1 at the repo root, which run this
inside the backend container via `docker compose exec`), so new matching
jobs — and the push notification about them — show up even on a day the
user never opens JobPilot.

Run manually with: docker compose exec backend python -m app.scripts.run_daily_sweep
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.api.v1.routers.jobs import run_auto_import_for_user
from app.db.session import AsyncSessionLocal, engine
from app.models.user import User
from app.services.sweep_errors import SweepNotReady

logger = logging.getLogger("jobflow.sweep")


async def run() -> None:
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User))).scalars().all()
        logger.info("Daily sweep: %d user(s) to check.", len(users))
        for user in users:
            try:
                result = await run_auto_import_for_user(user, db)
            except SweepNotReady as exc:
                # No career profile yet, or nothing in it to search on —
                # normal for a brand-new account, not worth alarming about.
                # Was `except HTTPException`, which only worked because the
                # service reached into FastAPI from a context with no request.
                logger.info("Skipped %s: %s", user.email, exc)
                continue
            except Exception:
                logger.exception("Sweep failed for %s", user.email)
                continue
            logger.info("Swept %s: imported %d job(s).", user.email, result.imported)
    await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run())
