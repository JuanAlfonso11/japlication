"""The durable half of the external-search cache.

What it protects, in one sentence: pressing "Agregar a la cola" on a result
that is still on screen must work, even though the process that answered the
search has been replaced since.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.external_job_cache import ExternalJobCache
from app.models.job import Job
from app.services.external_jobs import result_cache


def _result(external_id: str = "him-1", **overrides) -> dict:
    """A normalized search result, shaped exactly as the search endpoints
    store it: `model_dump(mode="json")` of an ExternalJobResult."""
    payload = {
        "external_id": external_id,
        "source": "himalayas",
        "source_url": f"https://himalayas.app/jobs/{external_id}",
        "title": "Ingeniero backend senior",
        "company": "Acme",
        "location": "Worldwide (remoto)",
        "remote_type": "remote",
        "employment_type": "full_time",
        "seniority": "senior",
        "description": "Buscamos alguien que sepa de colas y de Postgres.",
        "requirements": ["5 años con Python"],
        "responsibilities": ["Mantener el pipeline de ingesta"],
        "skills_required": [{"name": "Python", "importance": "required"}],
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "posted_at": "2026-09-10T12:00:00Z",
        "posted_at_text": None,
        "via": None,
        "apply_options": [],
        "thumbnail": None,
    }
    payload.update(overrides)
    return payload


async def _age_row(source: str, external_id: str, hours: int) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(ExternalJobCache)
            .where(ExternalJobCache.source == source, ExternalJobCache.external_id == external_id)
            .values(cached_at=datetime.now(timezone.utc) - timedelta(hours=hours))
        )
        await session.commit()


async def test_result_survives_and_comes_back_whole():
    await result_cache.remember("himalayas", [_result()])

    stored = await result_cache.get("himalayas", "him-1")

    assert stored == _result()


async def test_unknown_result_is_a_miss_not_an_error():
    assert await result_cache.get("himalayas", "nope") is None


async def test_results_without_an_id_are_skipped():
    # normalize_results already drops these, but a result with no id cannot
    # be imported later either way — storing one would only ever produce a
    # row nothing can look up.
    await result_cache.remember("himalayas", [_result(external_id="")])

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(ExternalJobCache))).scalars().all()
    assert rows == []


async def test_a_result_past_its_ttl_is_not_served():
    # Checked on read, not only by the sweep: a row can outlive its TTL
    # between sweeps, and serving it would import a posting this cache
    # already considers stale.
    await result_cache.remember("himalayas", [_result()])
    await _age_row("himalayas", "him-1", settings.EXTERNAL_JOBS_CACHE_TTL_HOURS + 1)

    assert await result_cache.get("himalayas", "him-1") is None


async def test_seeing_a_result_again_refreshes_it():
    await result_cache.remember("himalayas", [_result(title="Título viejo")])
    await _age_row("himalayas", "him-1", settings.EXTERNAL_JOBS_CACHE_TTL_HOURS + 1)

    await result_cache.remember("himalayas", [_result(title="Título nuevo")])

    stored = await result_cache.get("himalayas", "him-1")
    assert stored is not None
    assert stored["title"] == "Título nuevo"


async def test_one_provider_does_not_shadow_another():
    await result_cache.remember("himalayas", [_result(external_id="same-id")])
    await result_cache.remember(
        "remotive", [_result(external_id="same-id", source="remotive", title="Otro puesto")]
    )

    himalayas = await result_cache.get("himalayas", "same-id")
    remotive = await result_cache.get("remotive", "same-id")
    assert himalayas is not None and remotive is not None
    assert himalayas["title"] != remotive["title"]


async def test_import_works_after_the_in_memory_cache_is_gone(async_client, user_and_headers):
    """The whole point. No search has run in this process, so every
    connector's own dict is empty — exactly the state a restart leaves
    behind. The import must still succeed from the stored copy."""
    _user, headers = user_and_headers
    await result_cache.remember("himalayas", [_result()])

    response = await async_client.post(
        "/jobs/search/import",
        json={"source": "himalayas", "external_id": "him-1"},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Ingeniero backend senior"
    assert body["company"] == "Acme"
    # The field the JSONB round-trip is most likely to lose: it goes into a
    # timestamptz column, and it left here as a string.
    assert body["posted_at"] is not None

    async with AsyncSessionLocal() as session:
        jobs = (await session.execute(select(Job))).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].posted_at is not None


async def test_expired_import_still_says_search_again(async_client, user_and_headers):
    _user, headers = user_and_headers
    await result_cache.remember("himalayas", [_result()])
    await _age_row("himalayas", "him-1", settings.EXTERNAL_JOBS_CACHE_TTL_HOURS + 1)

    response = await async_client.post(
        "/jobs/search/import",
        json={"source": "himalayas", "external_id": "him-1"},
        headers=headers,
    )

    assert response.status_code == 404


async def test_a_payload_an_older_build_wrote_is_a_404_not_a_500(async_client, user_and_headers):
    """The stored shape is whatever the build that wrote it used. A payload
    that no longer validates has to fail the way a missing one does — asking
    for a new search — not as a server error."""
    _user, headers = user_and_headers
    async with AsyncSessionLocal() as session:
        session.add(
            ExternalJobCache(
                source="himalayas",
                external_id="him-old",
                payload={"external_id": "him-old", "source": "himalayas", "title": "Sin empresa"},
            )
        )
        await session.commit()

    response = await async_client.post(
        "/jobs/search/import",
        json={"source": "himalayas", "external_id": "him-old"},
        headers=headers,
    )

    assert response.status_code == 404


async def test_a_feed_repeating_an_id_does_not_break_the_write():
    # Postgres refuses an ON CONFLICT DO UPDATE that touches the same row
    # twice in one statement, so the batch is keyed before it is sent.
    await result_cache.remember(
        "himalayas", [_result(title="Primera"), _result(title="Segunda")]
    )

    stored = await result_cache.get("himalayas", "him-1")
    assert stored is not None
    assert stored["title"] == "Segunda"
