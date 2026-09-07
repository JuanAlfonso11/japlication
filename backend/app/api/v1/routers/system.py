"""Lets each scheduled background script (scripts/*.ps1) report "I ran,
here's how it went" right after it runs, and lets the app show that back
to the user — Profile's "Estado del sistema" panel — without anyone
having to open Task Scheduler or `docker compose logs` to check whether
the sweep/backup/watchdog/stale-check machinery is actually alive.
"""

import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.system_heartbeat import SystemHeartbeat
from app.models.user import User
from app.schemas.system_heartbeat import HeartbeatInfo, HeartbeatRequest

router = APIRouter(prefix="/system", tags=["system"])


def _check_heartbeat_secret(x_heartbeat_secret: Optional[str]) -> None:
    # settings.SYSTEM_HEARTBEAT_SECRET is always populated by get_settings()
    # (env var if set, otherwise an auto-generated + persisted one) — so
    # this endpoint never silently accepts an unauthenticated caller.
    #
    # compare_digest, not `!=`: Python's string comparison returns as soon
    # as two bytes differ, so how long it takes to say "no" leaks how much
    # of the prefix was right, and a secret can be recovered a character at
    # a time. The window is small over a network, but a constant-time
    # comparison is free and removes the question.
    expected = settings.SYSTEM_HEARTBEAT_SECRET or ""
    if not x_heartbeat_secret or not secrets.compare_digest(x_heartbeat_secret, expected):
        raise HTTPException(status_code=401, detail="Invalid heartbeat secret.")


@router.post("/heartbeat", status_code=204)
async def post_heartbeat(
    payload: HeartbeatRequest,
    x_heartbeat_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    _check_heartbeat_secret(x_heartbeat_secret)

    stmt = (
        pg_insert(SystemHeartbeat)
        .values(
            job_name=payload.job_name,
            last_run_at=datetime.now(timezone.utc),
            last_status=payload.status,
            detail=payload.detail,
        )
        .on_conflict_do_update(
            index_elements=[SystemHeartbeat.job_name],
            set_={
                "last_run_at": datetime.now(timezone.utc),
                "last_status": payload.status,
                "detail": payload.detail,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()


@router.get("/status", response_model=list[HeartbeatInfo])
async def get_system_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[HeartbeatInfo]:
    rows = (await db.execute(select(SystemHeartbeat).order_by(SystemHeartbeat.job_name))).scalars().all()
    return [HeartbeatInfo.model_validate(r) for r in rows]
