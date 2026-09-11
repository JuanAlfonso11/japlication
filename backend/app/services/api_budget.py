"""Daily call budget for external job-search providers with a monthly
quota, so an unattended background process (the every-2-hours sweep,
scripts/daily-job-sweep.ps1) can never silently blow through it before the
month is over.

Adzuna: 1,000 calls/month (docs/PUBLIC_APIS_RESEARCH.md #9) — generous, but
capped here too for symmetry and because Discover searches add on top of
the sweep's own usage.

SerpApi: 250 searches/month, 50/hour (docs/PUBLIC_APIS_RESEARCH.md #12) —
its own docs say outright "no es para polling continuo". A plain 2-hour
schedule alone is 12 calls/day (~360/month), already over quota with zero
manual searches.

DAILY_CALL_BUDGET=8 keeps every quota-limited provider at 8*30=240
calls/month even if every single call came from the unattended sweep —
under both quotas with room left over for manual Discover searches.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import AsyncSessionLocal
from app.models.api_call_budget import ApiCallBudget

DAILY_CALL_BUDGET = 8

# LinkedIn (Bright Data) is billed per record, and a run is where that money
# goes. Its service consumes this budget itself, right before starting a run,
# so a search answered from cache never counts against the day — the router
# skips it for that reason.
QUOTA_LIMITED_PROVIDERS = {"adzuna", "serpapi", "linkedin"}


async def try_consume_budget(provider: str) -> bool:
    """Atomically increments today's call counter for `provider` and
    returns whether this call is still within DAILY_CALL_BUDGET. Providers
    outside QUOTA_LIMITED_PROVIDERS (no monthly quota to protect) always
    return True without touching the database.

    Opens its own short-lived session (AsyncSessionLocal) rather than
    accepting the caller's request-scoped one: every provider search runs
    concurrently via asyncio.gather in both call sites (Discover's
    aggregate search, the auto-import sweep), and a single AsyncSession
    isn't safe to use from multiple coroutines interleaved on the same
    event loop — sharing one would risk "session is already in use"
    errors or corrupted state under concurrent access.

    Deliberately "consume first, ask permission after": the counter is
    incremented unconditionally, then compared to the budget, rather than
    a separate SELECT-then-maybe-increment — a single atomic upsert avoids
    a check-then-act race, at the cost of the counter climbing past
    DAILY_CALL_BUDGET on a day with many rejected attempts. That's fine:
    only the "count <= budget" boolean is ever read, never the raw count
    itself, and a fresh day starts a fresh row at 0 regardless."""
    if provider not in QUOTA_LIMITED_PROVIDERS:
        return True

    today = datetime.now(timezone.utc).date()
    async with AsyncSessionLocal() as db:
        stmt = (
            pg_insert(ApiCallBudget)
            .values(provider=provider, call_date=today, call_count=1)
            .on_conflict_do_update(
                index_elements=[ApiCallBudget.provider, ApiCallBudget.call_date],
                set_={"call_count": ApiCallBudget.call_count + 1},
            )
            .returning(ApiCallBudget.call_count)
        )
        new_count = (await db.execute(stmt)).scalar_one()
        await db.commit()
    return new_count <= DAILY_CALL_BUDGET
