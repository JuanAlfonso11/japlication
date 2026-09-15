"""Search results kept where a restart cannot reach them.

A search fans out to fifteen sources and normalizes what comes back.
"Agregar a la cola" then posts only `{source, external_id}` and the server
rebuilds the posting from the result it already has — the alternative being
a second request to a source that may be keyed, rate-limited, behind an
open circuit breaker, or just slow, for a posting it already answered about
a moment ago.

Each connector kept that copy in a module-level dict. Those dicts are still
there and are still the fast path; what they are not is durable. Anything
that replaces the process empties them — the watchdog recovering a
container every 15 minutes, `docker compose up -d --build`, shipping an
APK, a plain reboot — and the 15-minute TTL empties them on its own anyway.
The user, who has a list of results on screen and no idea any of that
happened, presses the button and is told the result expired and they should
search again. On a phone, from the bottom of a long list, that is the whole
find lost.

So the normalized results are also written here, once per search, at the
point where they are already in hand. Reads try the in-memory dict first
and fall back to this table.

Deliberately NOT a general-purpose cache:

  * TTL is in hours, not days. The copy is for the gap between seeing a
    result and acting on it, not a private index of the job market. A
    posting a week old is likely filled, and importing it would put a dead
    listing in the swipe queue, which is worse than asking for a new search.

  * Expiry is checked on read as well as swept on write. A row that outlives
    its TTL between sweeps must not be served just because the cleanup has
    not run yet.

  * Its own session, never the caller's. Every write site is inside an
    asyncio.gather fan-out, and one AsyncSession shared between coroutines
    interleaved on the same loop corrupts its state — the same reason
    app.services.api_budget opens its own. Some of those writes also come
    from "straggler" tasks that finish after their request has been answered
    and its session closed.

  * Never fatal. A failure here means one button press falls back to
    "search again", which is exactly where things stood before this existed.
    It must not turn a search that worked into a 500.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.external_job_cache import ExternalJobCache

logger = logging.getLogger(__name__)

# Rows are swept on write, but at most this often: a sweep on every search
# would mean a DELETE per search for a table that is almost always already
# clean. Module-level because it is a throttle, not state anyone depends on
# — a restart just means the next search sweeps, which is harmless.
_SWEEP_INTERVAL = timedelta(minutes=10)
_last_sweep: Optional[datetime] = None


def _ttl() -> timedelta:
    return timedelta(hours=settings.EXTERNAL_JOBS_CACHE_TTL_HOURS)


async def remember(source: str, results: list[dict[str, Any]]) -> None:
    """Stores normalized results for later import. Never raises."""
    now = datetime.now(timezone.utc)
    # Keyed rather than appended: Postgres refuses an ON CONFLICT DO UPDATE
    # that would touch the same row twice in one statement, and a feed
    # repeating an id inside a single page is not hypothetical — several of
    # these return the same posting under two categories. Last one wins,
    # which is the same rule the upsert applies across statements.
    by_key: dict[str, dict[str, Any]] = {}
    for r in results:
        external_id = r.get("external_id")
        if not external_id:
            continue
        by_key[str(external_id)] = {
            "source": source,
            "external_id": str(external_id),
            "payload": r,
            "cached_at": now,
        }
    rows = list(by_key.values())
    if not rows:
        return

    try:
        async with AsyncSessionLocal() as session:
            stmt = pg_insert(ExternalJobCache).values(rows)
            # A posting seen again in a later search refreshes its copy
            # rather than being skipped: the newer payload is the better one,
            # and the timestamp is what keeps it importable.
            await session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["source", "external_id"],
                    set_={"payload": stmt.excluded.payload, "cached_at": stmt.excluded.cached_at},
                )
            )
            await session.commit()
            await _sweep(session)
    except Exception:  # noqa: BLE001 - caching must never break a search
        logger.warning("could not cache %d results from %s", len(rows), source, exc_info=True)


async def get(source: str, external_id: str) -> Optional[dict[str, Any]]:
    """Returns the stored result, or None if it was never stored or has
    outlived its TTL. Never raises."""
    cutoff = datetime.now(timezone.utc) - _ttl()
    try:
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    select(ExternalJobCache).where(
                        ExternalJobCache.source == source,
                        ExternalJobCache.external_id == str(external_id),
                        # Checked here and not only in the sweep: a row can
                        # outlive its TTL between sweeps, and serving it would
                        # import a posting this cache already considers stale.
                        ExternalJobCache.cached_at >= cutoff,
                    )
                )
            ).scalar_one_or_none()
            return dict(row.payload) if row else None
    except Exception:  # noqa: BLE001 - a miss is a valid answer; a 500 is not
        logger.warning("could not read cached result %s/%s", source, external_id, exc_info=True)
        return None


async def _sweep(session) -> None:
    """Deletes rows past their TTL, at most every _SWEEP_INTERVAL."""
    global _last_sweep
    now = datetime.now(timezone.utc)
    if _last_sweep is not None and now - _last_sweep < _SWEEP_INTERVAL:
        return
    _last_sweep = now
    await session.execute(delete(ExternalJobCache).where(ExternalJobCache.cached_at < now - _ttl()))
    await session.commit()
