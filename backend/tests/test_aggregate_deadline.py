"""The aggregate search must answer before the frontend gives up.

Discover's client aborts at 20s (REQUEST_TIMEOUT_MS). The aggregate used to
wait for its slowest provider, which can take up to its own 20-30s httpx
timeout — so one slow upstream turned searches into "the server took too long"
errors, and every retry piled another full fan-out onto the unfinished ones.
"""

import asyncio
import time

import pytest

from app.api.v1.routers import jobs


@pytest.mark.asyncio
async def test_aggregate_answers_by_the_deadline_and_keeps_slow_providers_running(
    async_client, user_and_headers, monkeypatch
):
    _user, headers = user_and_headers
    release = asyncio.Event()

    async def fake_provider(provider, *_args):
        if provider == "hackernews":
            await release.wait()  # stands in for an upstream that hangs
        return provider, [], None

    monkeypatch.setattr(jobs, "_SEARCH_PROVIDERS", {"himalayas", "hackernews"})
    monkeypatch.setattr(jobs, "_run_search_provider", fake_provider)
    monkeypatch.setattr(jobs, "_AGGREGATE_DEADLINE_SECONDS", 0.2)

    started = time.monotonic()
    response = await async_client.get("/jobs/search/aggregate", params={"q": "developer"}, headers=headers)
    elapsed = time.monotonic() - started

    assert response.status_code == 200, response.text
    assert elapsed < 2, f"the aggregate waited for the slow provider ({elapsed:.1f}s)"
    sources = {s["provider"]: s for s in response.json()["sources"]}
    assert sources["himalayas"]["error"] is None
    # Worded so Discover shows its neutral "buscando…" chip, not a red error.
    assert "segundo plano" in sources["hackernews"]["error"]

    # Not cancelled: still running, so a slow feed can fill its cache for next time.
    assert len(jobs._stragglers) == 1
    straggler = next(iter(jobs._stragglers))
    assert not straggler.done()
    release.set()
    await straggler
    assert not straggler.cancelled()
    await asyncio.sleep(0)  # let the done-callback drop the reference
    assert jobs._stragglers == set()
