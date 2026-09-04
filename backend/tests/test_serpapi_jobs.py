import asyncio

from app.services import serpapi_jobs

SAMPLE_JOB = {
    "job_id": "abc123==",
    "title": "Senior Backend Engineer",
    "company_name": "Acme Corp",
    "location": "Anywhere",
    "via": "LinkedIn",
    "description": "We need a Senior Backend Engineer with Python and Docker experience.",
    "detected_extensions": {
        "posted_at": "3 days ago",
        "salary": "$120K–$150K a year",
        "schedule_type": "Full-time",
        "work_from_home": True,
    },
    "job_highlights": [
        {"title": "Qualifications", "items": ["5+ years experience", "Strong Python skills"]},
        {"title": "Responsibilities", "items": ["Own backend services"]},
    ],
    "apply_options": [{"title": "LinkedIn", "link": "https://www.linkedin.com/jobs/view/123"}],
    "source_link": "https://www.linkedin.com/jobs/view/123",
    "share_link": "https://www.google.com/search?ibp=htl;jobs",
}


def test_is_configured_requires_key(monkeypatch):
    monkeypatch.setattr(serpapi_jobs.settings, "SERPAPI_API_KEY", None)
    assert serpapi_jobs.is_configured() is False
    monkeypatch.setattr(serpapi_jobs.settings, "SERPAPI_API_KEY", "key")
    assert serpapi_jobs.is_configured() is True


def test_normalize_maps_fields():
    normalized = serpapi_jobs._normalize(SAMPLE_JOB)
    assert normalized["title"] == "Senior Backend Engineer"
    assert normalized["company"] == "Acme Corp"
    assert normalized["serpapi_job_id"] == "abc123=="
    assert normalized["source"] == "serpapi"
    assert normalized["source_url"] == "https://www.linkedin.com/jobs/view/123"
    assert normalized["remote_type"] == "remote"
    assert normalized["employment_type"] == "full_time"
    assert normalized["requirements"] == ["5+ years experience", "Strong Python skills"]
    assert normalized["responsibilities"] == ["Own backend services"]
    assert normalized["salary_min"] == 120000
    assert normalized["salary_max"] == 150000
    assert normalized["salary_currency"] == "USD"
    assert normalized["via"] == "LinkedIn"
    assert normalized["posted_at"] is not None


def test_normalize_skips_missing_id_or_title():
    assert serpapi_jobs._normalize({"title": "X"}) is None
    assert serpapi_jobs._normalize({"job_id": "1"}) is None


def test_search_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(serpapi_jobs.settings, "SERPAPI_API_KEY", None)
    try:
        asyncio.run(serpapi_jobs.search_serpapi_jobs(q="backend"))
        assert False, "expected SerpApiError"
    except serpapi_jobs.SerpApiError:
        pass


def test_search_fetches_and_filters(monkeypatch):
    monkeypatch.setattr(serpapi_jobs.settings, "SERPAPI_API_KEY", "key")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"jobs_results": [SAMPLE_JOB]}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(serpapi_jobs.httpx, "AsyncClient", FakeAsyncClient)
    serpapi_jobs._search_cache.clear()

    data = asyncio.run(serpapi_jobs.search_serpapi_jobs(q="backend"))
    assert len(data["results"]) == 1
    assert serpapi_jobs.get_cached_result("abc123==") is not None

    data = asyncio.run(serpapi_jobs.search_serpapi_jobs(q="backend", experience_level_filter="entry"))
    assert data["results"] == []
