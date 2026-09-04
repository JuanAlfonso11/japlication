import asyncio

from app.services import jobicy

SAMPLE_RAW = {
    "id": 42,
    "url": "https://jobicy.com/jobs/backend-engineer-42",
    "jobTitle": "Backend Engineer",
    "companyName": "Acme",
    "jobIndustry": ["Engineering"],
    "jobType": ["Full-time"],
    "jobGeo": "USA",
    "jobLevel": "Midweight",
    "jobExcerpt": "We need a backend engineer.",
    "jobDescription": "<p>We need a Backend Engineer with Python and Docker experience.</p>",
    "pubDate": "2026-01-01 00:00:00",
    "salaryMin": 80000,
    "salaryMax": 100000,
    "salaryCurrency": "USD",
}


def test_normalize_maps_core_fields_and_native_level():
    normalized = jobicy._normalize(SAMPLE_RAW)
    assert normalized["jobicy_job_id"] == "42"
    assert normalized["source"] == "jobicy"
    assert normalized["remote_type"] == "remote"
    assert normalized["seniority"] == "mid"  # "Midweight" normalized via experience_level
    assert normalized["salary_min"] == 80000
    assert normalized["salary_currency"] == "USD"


def test_search_applies_level_filter_client_side(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"jobCount": 1, "jobs": [SAMPLE_RAW]}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(jobicy.httpx, "AsyncClient", FakeAsyncClient)
    jobicy._search_cache.clear()

    data = asyncio.run(jobicy.search_jobicy_jobs(experience_level_filter="mid"))
    assert len(data["results"]) == 1
    assert jobicy.get_cached_result("42") is not None

    data = asyncio.run(jobicy.search_jobicy_jobs(experience_level_filter="senior"))
    assert data["results"] == []


def test_search_maps_geo_param(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"jobs": []}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            assert params["geo"] == "usa"
            return FakeResponse()

    monkeypatch.setattr(jobicy.httpx, "AsyncClient", FakeAsyncClient)
    asyncio.run(jobicy.search_jobicy_jobs(location="USA"))


def test_search_retries_without_geo_on_400(monkeypatch):
    """Jobicy 400s on any geoSlug outside its own curated ~55-country list
    (e.g. "dominican-republic", which Discover's location dropdown offers
    but Jobicy simply has no coverage for) — must gracefully retry without
    `geo` instead of surfacing that as a search error, same as every other
    provider degrades on a location it doesn't recognize."""
    calls = []

    class FakeResponse:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body

        def json(self):
            return self._body

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            calls.append(dict(params or {}))
            if "geo" in (params or {}):
                return FakeResponse(400, {"success": False, "error": "Invalid 'geo' value."})
            return FakeResponse(200, {"jobs": []})

    monkeypatch.setattr(jobicy.httpx, "AsyncClient", FakeAsyncClient)
    data = asyncio.run(jobicy.search_jobicy_jobs(location="Dominican Republic"))

    assert data["results"] == []  # succeeded rather than raising
    assert len(calls) == 2
    assert calls[0]["geo"] == "dominican republic"
    assert "geo" not in calls[1]
