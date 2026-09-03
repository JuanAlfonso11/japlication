import asyncio

from app.services import remotejobs_org

SAMPLE_RAW = {
    "id": 7,
    "title": "Senior Backend Engineer",
    "url": "https://remotejobs.org/jobs/7",
    "apply_url": "https://remotejobs.org/jobs/7/apply",
    "company": {"name": "Acme", "logo_url": None, "website": None, "url": None},
    "category": {"name": "Programming", "slug": "programming"},
    "location": "Worldwide",
    "salary_min": 100000,
    "salary_max": 140000,
    "salary_text": "$100k-140k",
    "type": "full-time",
    "description": "<p>We need a Senior Backend Engineer with Python experience.</p>",
    "posted_at": "2026-01-01T00:00:00",
}


def test_normalize_maps_core_fields_and_infers_senior():
    normalized = remotejobs_org._normalize(SAMPLE_RAW)
    assert normalized["remotejobs_org_job_id"] == "7"
    assert normalized["source"] == "remotejobs_org"
    assert normalized["source_url"] == "https://remotejobs.org/jobs/7/apply"
    assert normalized["company"] == "Acme"
    assert normalized["employment_type"] == "full_time"
    assert normalized["seniority"] == "senior"


def test_search_reads_data_and_pagination_envelope(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"data": [SAMPLE_RAW], "pagination": {"total": 1, "limit": 20, "offset": 0, "has_more": False}}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(remotejobs_org.httpx, "AsyncClient", FakeAsyncClient)
    remotejobs_org._search_cache.clear()

    data = asyncio.run(remotejobs_org.search_remotejobs_org_jobs())
    assert len(data["results"]) == 1
    assert data["has_more"] is False
    assert remotejobs_org.get_cached_result("7") is not None
