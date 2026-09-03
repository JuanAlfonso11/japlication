import asyncio

from app.services import themuse

SAMPLE_RAW = {
    "id": 999,
    "name": "Senior Backend Engineer",
    "contents": "<p>We need a Senior Backend Engineer with Python and AWS experience.</p>",
    "type": "Full Time",
    "publication_date": "2026-01-01T00:00:00Z",
    "company": {"id": 1, "short_name": "acme", "name": "Acme"},
    "locations": [{"name": "Remote"}],
    "levels": [{"name": "Senior Level", "short_name": "senior"}],
    "categories": [{"name": "Engineering"}],
    "tags": ["some-internal-tag"],
    "refs": {"landing_page": "https://www.themuse.com/jobs/acme/senior-backend-engineer"},
}


def test_normalize_maps_core_fields_and_native_level():
    normalized = themuse._normalize(SAMPLE_RAW)
    assert normalized["themuse_job_id"] == "999"
    assert normalized["source"] == "themuse"
    assert normalized["source_url"].endswith("senior-backend-engineer")
    assert normalized["company"] == "Acme"
    assert normalized["remote_type"] == "remote"
    assert normalized["seniority"] == "senior"
    assert normalized["employment_type"] == "full_time"


def test_search_passes_native_location_and_level_params(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"page": 0, "page_count": 1, "results": [SAMPLE_RAW]}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            assert params["location"] == "Remote"
            assert params["level"] == "Senior Level"
            return FakeResponse()

    monkeypatch.setattr(themuse.httpx, "AsyncClient", FakeAsyncClient)
    themuse._search_cache.clear()

    data = asyncio.run(themuse.search_themuse_jobs(location="Remote", experience_level_filter="senior"))
    assert len(data["results"]) == 1
    assert data["has_more"] is False
    assert themuse.get_cached_result("999") is not None


def test_search_filters_by_keyword_client_side(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"page": 0, "page_count": 1, "results": [SAMPLE_RAW]}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(themuse.httpx, "AsyncClient", FakeAsyncClient)
    data = asyncio.run(themuse.search_themuse_jobs(q="frontend designer"))
    assert data["results"] == []
