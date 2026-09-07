"""Records what failed, where, and to whom — in one place you can query.

Before this, diagnosing a problem meant `docker compose logs backend` and
hoping the relevant lines hadn't rotated away, and a crash in the phone's
WebView left no trace anywhere at all.

Three properties this is built around:

**It must never make things worse.** Logging is a diagnostic aid, not a
feature: if writing the log row fails (the database is down — which is
exactly when errors spike), that failure is swallowed and the original error
still reaches the user unchanged. An error handler that can itself raise is
how a small outage becomes a total one.

**It must never log credentials.** The request body is deliberately not
captured. The first thing a POST to /auth/login carries is a password, and
"log everything" would turn a debugging convenience into a credential leak.
Query strings are dropped for the same reason. What's kept is where the
error came from and what broke, never the data it broke on.

**It must be findable.** Every request gets an id, the error response
carries it, and it's stored alongside the row — so "me salió un error" turns
into a lookup instead of an archaeology session.
"""

import logging
import traceback
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.error_log import ErrorLog

logger = logging.getLogger("jobflow.errors")

# Tracebacks and stacks are unbounded in principle; a runaway recursion
# produces megabytes of frames. Keep the head, which is where the cause is.
MAX_STACK_CHARS = 12_000
MAX_MESSAGE_CHARS = 2_000


def new_request_id() -> str:
    """Short enough for a person to read off a screen and repeat."""
    return uuid.uuid4().hex[:12]


def _truncate(value: Optional[str], limit: int) -> Optional[str]:
    if value is None:
        return None
    if len(value) <= limit:
        return value
    return value[:limit] + f"\n… [recortado, {len(value) - limit} caracteres más]"


async def record_error(
    *,
    request_id: str,
    source: str,
    message: str,
    kind: Optional[str] = None,
    stack: Optional[str] = None,
    method: Optional[str] = None,
    path: Optional[str] = None,
    status_code: Optional[int] = None,
    user_id=None,
    user_agent: Optional[str] = None,
    url: Optional[str] = None,
    level: str = "error",
    db: Optional[AsyncSession] = None,
) -> None:
    """Persists one error. Never raises.

    Always logs to stdout first: that path has no dependencies, so even if
    the database write below fails the error is still visible in
    `docker compose logs`.
    """
    logger.error(
        "[%s] %s %s -> %s: %s",
        request_id,
        method or source,
        path or url or "-",
        kind or "error",
        (message or "")[:500],
    )

    row = ErrorLog(
        request_id=request_id,
        source=source,
        level=level,
        kind=kind,
        message=_truncate(message, MAX_MESSAGE_CHARS) or "(sin mensaje)",
        stack=_truncate(stack, MAX_STACK_CHARS),
        method=method,
        path=path,
        status_code=status_code,
        user_id=user_id,
        user_agent=_truncate(user_agent, 500),
        url=_truncate(url, 1000),
    )

    try:
        if db is not None:
            db.add(row)
            await db.commit()
            return

        # A session of its own: the request's session is very often already
        # poisoned by the exception we're here to record (a failed flush
        # leaves it needing a rollback), so reusing it would fail for a
        # reason that has nothing to do with logging.
        async with AsyncSessionLocal() as session:
            session.add(row)
            await session.commit()
    except Exception:  # noqa: BLE001
        # Deliberately silent beyond stdout. See the module docstring: the
        # user's original error must reach them unchanged, and a logging
        # failure must not become a second, more confusing one.
        logger.exception("[%s] No se pudo persistir el error en la base.", request_id)


def format_exception(exc: BaseException) -> tuple[str, str, str]:
    """Returns (kind, message, stack) for an exception."""
    kind = type(exc).__name__
    message = str(exc) or kind
    stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return kind, message, stack
