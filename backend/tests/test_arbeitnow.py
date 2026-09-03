import asyncio

from app.services import arbeitnow

SAMPLE_RAW = {
    "slug": "backend-engineer-acme",
    "company_name": "Acme GmbH",
    "title": "Backend Engineer",
    "description": "<p>We need a Backend Engineer with 3+ years of experience in Python and PostgreSQL.</p>",
    "remote": True,
    "url": "https://www.arbeitnow.com/jobs/companies/acme/backend-engineer-acme",
    "tags": ["Python", "PostgreSQL", "Remote"],
    "job_types": ["Full-time"],
    "location": "Berlin, Germany",
    "created_at": 1700000000,
}


def test_normalize_maps_core_fields_and_infers_level():
    normalized = arbeitnow._normalize(SAMPLE_RAW)
    assert normalized["arbeitnow_job_id"] == "backend-engineer-acme"
    assert normalized["source"] == "arbeitnow"
    assert normalized["title"] == "Backend Engineer"
    assert normalized["company"] == "Acme GmbH"
    assert normalized["remote_type"] == "remote"
    assert normalized["source_url"].endswith("backend-engineer-acme")
    skill_names = {s["name"] for s in normalized["skills_required"]}
    assert "Python" in skill_names
    assert "PostgreSQL" in skill_names


def test_normalize_traineeship_maps_to_internship():
    raw = dict(SAMPLE_RAW, job_types=["Traineeship"])
    normalized = arbeitnow._normalize(raw)
    assert normalized["seniority"] == "internship"


def test_search_filters_by_remote_type_and_populates_cache(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"data": [SAMPLE_RAW], "links": {"next": None}}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(arbeitnow.httpx, "AsyncClient", FakeAsyncClient)
    arbeitnow._search_cache.clear()

    data = asyncio.run(arbeitnow.search_arbeitnow_jobs(remote_type_filter="remote"))
    assert len(data["results"]) == 1
    assert arbeitnow.get_cached_result("backend-engineer-acme") is not None

    # An onsite-only job should be dropped when filtering for remote_type="remote".
    onsite = dict(
        SAMPLE_RAW,
        slug="onsite-role",
        remote=False,
        location="Munich, Germany",
        description="<p>This is an on-site role based in our Munich office, 3+ years Python required.</p>",
    )

    class FakeResponseOnsite(FakeResponse):
        def json(self):
            return {"data": [onsite], "links": {"next": None}}

    class FakeAsyncClientOnsite(FakeAsyncClient):
        async def get(self, url, params=None):
            return FakeResponseOnsite()

    monkeypatch.setattr(arbeitnow.httpx, "AsyncClient", FakeAsyncClientOnsite)
    data = asyncio.run(arbeitnow.search_arbeitnow_jobs(remote_type_filter="remote"))
    assert data["results"] == []


def test_search_raises_clean_error_on_bad_status(monkeypatch):
    import pytest

    class FakeResponse:
        status_code = 500

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(arbeitnow.httpx, "AsyncClient", FakeAsyncClient)
    with pytest.raises(arbeitnow.ArbeitnowError):
        asyncio.run(arbeitnow.search_arbeitnow_jobs())
