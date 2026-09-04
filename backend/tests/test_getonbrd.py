import asyncio

from app.services import getonbrd

SAMPLE_JOB = {
    "id": "senior-backend-engineer-acme-remote",
    "type": "job",
    "attributes": {
        "title": "Senior Backend Engineer",
        "description": "<div>We need a Senior Backend Engineer with Python and Docker experience.</div>",
        "functions": "",
        "desirable": "",
        "benefits": "",
        "remote": True,
        "remote_modality": "fully_remote",
        "countries": ["Remote"],
        "category_name": "Programming",
        "min_salary": 3000,
        "max_salary": 5000,
        "published_at": 1788460925,
        "modality": {"data": {"id": "1", "type": "modality", "attributes": {"name": "Full time", "locale_key": "full_time"}}},
        "seniority": {"data": {"id": "4", "type": "seniority", "attributes": {"name": "Senior", "locale_key": "senior"}}},
        "company": {"data": {"id": "acme", "type": "company", "attributes": {"name": "Acme Corp"}}},
    },
    "links": {"public_url": "https://www.getonbrd.com/jobs/senior-backend-engineer-acme-remote"},
}


def test_normalize_maps_fields():
    normalized = getonbrd._normalize(SAMPLE_JOB)
    assert normalized["title"] == "Senior Backend Engineer"
    assert normalized["company"] == "Acme Corp"
    assert normalized["getonbrd_job_id"] == "senior-backend-engineer-acme-remote"
    assert normalized["source"] == "getonbrd"
    assert normalized["source_url"] == "https://www.getonbrd.com/jobs/senior-backend-engineer-acme-remote"
    assert normalized["remote_type"] == "remote"
    assert normalized["employment_type"] == "full_time"
    assert normalized["seniority"] == "senior"
    assert normalized["salary_min"] == 3000
    assert normalized["salary_currency"] == "USD"


def test_search_fetches_and_filters(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"data": [SAMPLE_JOB], "meta": {"page": 1, "per_page": 20, "total_pages": 1}}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            assert len(params["query"]) >= 3
            return FakeResponse()

    monkeypatch.setattr(getonbrd.httpx, "AsyncClient", FakeAsyncClient)
    getonbrd._search_cache.clear()

    data = asyncio.run(getonbrd.search_getonbrd_jobs(q="backend"))
    assert len(data["results"]) == 1
    assert getonbrd.get_cached_result("senior-backend-engineer-acme-remote") is not None

    data = asyncio.run(getonbrd.search_getonbrd_jobs(q="backend", experience_level_filter="entry"))
    assert data["results"] == []


def test_search_falls_back_to_broad_query_when_q_too_short(monkeypatch):
    seen_queries = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"data": [], "meta": {"page": 1, "per_page": 20, "total_pages": 1}}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            seen_queries.append(params["query"])
            return FakeResponse()

    monkeypatch.setattr(getonbrd.httpx, "AsyncClient", FakeAsyncClient)
    asyncio.run(getonbrd.search_getonbrd_jobs(q=None))
    asyncio.run(getonbrd.search_getonbrd_jobs(q="ab"))
    assert all(len(q) >= 3 for q in seen_queries)
