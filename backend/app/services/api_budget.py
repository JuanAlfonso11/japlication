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

# Per-provider overrides. Anything listed here is budgeted; anything else is
# unlimited. Kept as a dict rather than one global number because the
# providers protect different things: Adzuna and SerpApi protect a monthly
# *quota* (8/day is the real ceiling), while Anthropic protects a *bill*
# — it has no free tier to run out of, so the only thing standing between a
# runaway loop and a real invoice is a number like this one. 250/day is far
# above normal use (a sweep scores ~20 jobs every 2 hours) and exists to
# catch a bug, not to throttle the feature.
PROVIDER_DAILY_BUDGETS: dict[str, int] = {
    "adzuna": DAILY_CALL_BUDGET,
    "serpapi": DAILY_CALL_BUDGET,
    "anthropic": 250,
}

QUOTA_LIMITED_PROVIDERS = set(PROVIDER_DAILY_BUDGETS)


def budget_for(provider: str) -> int:
    return PROVIDER_DAILY_BUDGETS.get(provider, DAILY_CALL_BUDGET)


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
    return new_count <= budget_for(provider)
