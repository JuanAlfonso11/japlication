import asyncio

from app.services import remotive

SAMPLE_RAW = {
    "id": 555,
    "url": "https://remotive.com/remote-jobs/software-dev/backend-engineer-555",
    "title": "Backend Engineer",
    "company_name": "Widgets Inc",
    "category": "Software Development",
    "job_type": "full_time",
    "publication_date": "2026-01-01T00:00:00",
    "candidate_required_location": "USA Only",
    "salary": "$90,000 - $120,000",
    "description": "<p>We need a Backend Engineer with Python and PostgreSQL experience.</p>",
}


def test_normalize_maps_core_fields():
    normalized = remotive._normalize(SAMPLE_RAW)
    assert normalized["remotive_job_id"] == "555"
    assert normalized["source"] == "remotive"
    assert normalized["remote_type"] == "remote"
    assert normalized["employment_type"] == "full_time"
    assert normalized["location"] == "USA Only"
    assert normalized["salary_min"] == 90000
    assert normalized["salary_max"] == 120000
    assert normalized["salary_currency"] == "USD"


def test_normalize_internship_job_type():
    raw = dict(SAMPLE_RAW, job_type="internship")
    normalized = remotive._normalize(raw)
    assert normalized["seniority"] == "internship"


def test_search_passes_query_as_search_param_and_caches(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"job-count": 1, "jobs": [SAMPLE_RAW]}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            assert params["search"] == "backend"
            return FakeResponse()

    monkeypatch.setattr(remotive.httpx, "AsyncClient", FakeAsyncClient)
    remotive._search_cache.clear()

    data = asyncio.run(remotive.search_remotive_jobs(q="backend"))
    assert len(data["results"]) == 1
    assert remotive.get_cached_result("555") is not None


def test_search_filters_by_location_substring(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"jobs": [SAMPLE_RAW]}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(remotive.httpx, "AsyncClient", FakeAsyncClient)
    data = asyncio.run(remotive.search_remotive_jobs(location="Germany"))
    assert data["results"] == []
