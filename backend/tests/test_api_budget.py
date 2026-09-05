"""Integration tests for the daily call budget on quota-limited external
job-search providers (Adzuna, SerpApi) — regression coverage for the
"protect the monthly quota from an unattended background sweep" fix."""

from datetime import date

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.api_call_budget import ApiCallBudget
from app.services import api_budget


async def _current_count(provider: str) -> int:
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(ApiCallBudget).where(
                    ApiCallBudget.provider == provider, ApiCallBudget.call_date == date.today()
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
