"""Lets each scheduled background script (scripts/*.ps1) report "I ran,
here's how it went" right after it runs, and lets the app show that back
to the user — Profile's "Estado del sistema" panel — without anyone
having to open Task Scheduler or `docker compose logs` to check whether
the sweep/backup/watchdog/stale-check machinery is actually alive.
"""

import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.error_log import ErrorLog
from app.models.system_heartbeat import SystemHeartbeat
from app.models.user import User
from app.schemas.error_log import ClientErrorReport, ErrorLogEntry
from app.schemas.system_heartbeat import HeartbeatInfo, HeartbeatRequest
from app.services.error_logger import new_request_id, record_error

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


@router.post("/client-errors", status_code=204)
@limiter.limit("30/minute")
async def report_client_error(
    request: Request,
    payload: ClientErrorReport,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Lets the frontend report its own crashes.

    Without this, a JavaScript error in the phone's WebView was invisible:
    the user saw a broken screen and there was nothing to inspect afterwards
    — no console to open, no log to read. Now it lands in the same table as
    backend failures, so one list answers "what broke?" regardless of side.

    Rate-limited because it's an authenticated write reachable from client
    code: one render loop throwing on every frame could otherwise write
    thousands of rows a minute.
    """
    await record_error(
        request_id=getattr(request.state, "request_id", new_request_id()),
        source="frontend",
        kind=payload.kind,
        message=payload.message,
        stack=payload.stack,
        url=payload.url,
        user_id=current_user.id,
        user_agent=request.headers.get("user-agent"),
        db=db,
    )


@router.get("/errors", response_model=list[ErrorLogEntry])
async def list_errors(
    limit: int = Query(50, ge=1, le=200),
    source: Optional[str] = Query(None, pattern="^(backend|frontend)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ErrorLogEntry]:
    """The most recent failures, newest first — what Profile's system panel
    reads so you can diagnose from the phone instead of `docker compose logs`.

    Deliberately NOT filtered to the calling user: this is a single-operator
    app, and the point is to see everything that broke, including a tester's
    crash you'd otherwise never hear about.
    """
    stmt = select(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(limit)
    if source:
        stmt = stmt.where(ErrorLog.source == source)
    rows = (await db.execute(stmt)).scalars().all()
    return [ErrorLogEntry.model_validate(r) for r in rows]
