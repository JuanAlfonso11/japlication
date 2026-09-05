"""Pushes a "no movement in a while" reminder for applications stuck in
`applied` with no status change for STALE_AFTER_DAYS — meant to run once
a day (see scripts/check-stale-applications.ps1 +
scripts/install-stale-check-schedule.ps1), separate from the every-2-
hours job sweep, since re-checking staleness that often would just spam
the same reminder.

Re-reminds at most once every STALE_RENOTIFY_DAYS (tracked via
applications.stale_notified_at) rather than only ever once, since an
application can easily sit forgotten for months.

Run manually with: docker compose exec backend python -m app.scripts.check_stale_applications
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal, engine
from app.models.application import Application
from app.models.device_token import DeviceToken
from app.models.enums import ApplicationStatus
from app.services import push_notifications

logger = logging.getLogger("jobflow.stale_check")

STALE_AFTER_DAYS = 14
STALE_RENOTIFY_DAYS = 7


async def run() -> None:
    if not push_notifications.is_configured():
        logger.info("Push notifications not configured — nothing to do.")
        await engine.dispose()
        return

    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=STALE_AFTER_DAYS)
    renotify_cutoff = now - timedelta(days=STALE_RENOTIFY_DAYS)

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Application)
                .options(selectinload(Application.job))
                .where(
                    Application.status == ApplicationStatus.applied,
                    Application.applied_at.isnot(None),
                    Application.applied_at < stale_cutoff,
                )
            )
        ).scalars().all()

        notified = 0
        for app_row in rows:
            if app_row.stale_notified_at is not None and app_row.stale_notified_at > renotify_cutoff:
                continue

            tokens = (
                await db.execute(
                    select(DeviceToken.token).where(DeviceToken.user_id == app_row.user_id)
                )
            ).scalars().all()
            if not tokens:
                continue

            days_ago = (now - app_row.applied_at).days
            job_title = app_row.job.title if app_row.job else "una vacante"
            company = f" en {app_row.job.company}" if app_row.job else ""
            for device_token in tokens:
                push_notifications.send_push(
                    device_token,
                    "JobPilot",
                    f"Aplicaste a {job_title}{company} hace {days_ago} días sin novedades — "
                    "¿hiciste seguimiento?",
                )

            app_row.stale_notified_at = now
            notified += 1

        await db.commit()
        logger.info("Stale check: %d application(s) checked, %d reminder(s) sent.", len(rows), notified)
    await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run())
