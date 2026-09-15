"""Integration tests for the daily call budget on quota-limited external
job-search providers (Adzuna, SerpApi) — regression coverage for the
"protect the monthly quota from an unattended background sweep" fix."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.api_call_budget import ApiCallBudget
from app.services import api_budget


async def _current_count(provider: str) -> int:
    # UTC, matching api_budget.try_consume_budget. `date.today()` is the
    # machine's LOCAL date: this box runs at UTC-4, so between 20:00 and
    # 23:59 local the UTC date has already rolled over and this helper read a
    # different row than the code under test had just written — three tests
    # failing for four hours a day with no bug behind it. That is exactly how
    # a suite stops being run.
    today = datetime.now(timezone.utc).date()
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(ApiCallBudget).where(
                    ApiCallBudget.provider == provider, ApiCallBudget.call_date == today
                )
            )
        ).scalar_one_or_none()
        return row.call_count if row else 0


async def test_unlimited_provider_always_allowed_and_untracked():
    assert await api_budget.try_consume_budget("himalayas") is True
    assert await _current_count("himalayas") == 0


async def test_quota_limited_provider_allowed_up_to_daily_budget():
    for _ in range(api_budget.DAILY_CALL_BUDGET):
        assert await api_budget.try_consume_budget("adzuna") is True
    assert await _current_count("adzuna") == api_budget.DAILY_CALL_BUDGET


async def test_quota_limited_provider_rejected_past_daily_budget():
    for _ in range(api_budget.DAILY_CALL_BUDGET):
        await api_budget.try_consume_budget("serpapi")
    assert await api_budget.try_consume_budget("serpapi") is False
    assert await _current_count("serpapi") == api_budget.DAILY_CALL_BUDGET + 1


async def test_providers_tracked_independently():
    for _ in range(api_budget.DAILY_CALL_BUDGET):
        await api_budget.try_consume_budget("adzuna")
    # Adzuna is exhausted, but SerpApi's own budget is untouched.
    assert await api_budget.try_consume_budget("serpapi") is True
