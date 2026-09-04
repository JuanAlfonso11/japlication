import asyncio

from app.services import adzuna

SAMPLE_RESULT = {
    "id": 111,
    "title": "Senior Backend Engineer",
    "company": {"display_name": "Acme Corp"},
    "location": {"display_name": "London, UK"},
    "description": "We need a Senior Backend Engineer with Python and Docker experience.",
    "redirect_url": "https://www.adzuna.co.uk/jobs/111",
    "created": "2026-09-01T12:00:00Z",
    "contract_time": "full_time",
    "salary_min": 60000,
    "salary_max": 80000,
    "category": {"label": "IT Jobs"},
}


def test_is_configured_requires_both_keys(monkeypatch):
    monkeypatch.setattr(adzuna.settings, "ADZUNA_APP_ID", None)
    monkeypatch.setattr(adzuna.settings, "ADZUNA_APP_KEY", None)
    assert adzuna.is_configured() is False
    monkeypatch.setattr(adzuna.settings, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(adzuna.settings, "ADZUNA_APP_KEY", "key")
    assert adzuna.is_configured() is True


def test_country_slug_defaults_to_us():
    assert adzuna.country_slug(None) == "us"
    assert adzuna.country_slug("United Kingdom") == "gb"
    assert adzuna.country_slug("Somewhere Unmapped") == "us"


def test_normalize_maps_fields():
    normalized = adzuna._normalize(SAMPLE_RESULT, "gb")
    assert normalized["title"] == "Senior Backend Engineer"
    assert normalized["company"] == "Acme Corp"
    assert normalized["adzuna_job_id"] == "111"
    assert normalized["source"] == "adzuna"
    assert normalized["employment_type"] == "full_time"
    assert normalized["salary_currency"] == "GBP"


def test_search_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(adzuna.settings, "ADZUNA_APP_ID", None)
    monkeypatch.setattr(adzuna.settings, "ADZUNA_APP_KEY", None)
    try:
        asyncio.run(adzuna.search_adzuna_jobs(q="backend"))
        assert False, "expected AdzunaError"
    except adzuna.AdzunaError:
        pass


def test_search_fetches_and_filters(monkeypatch):
    monkeypatch.setattr(adzuna.settings, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(adzuna.settings, "ADZUNA_APP_KEY", "key")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"results": [SAMPLE_RESULT]}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(adzuna.httpx, "AsyncClient", FakeAsyncClient)
    adzuna._search_cache.clear()

    data = asyncio.run(adzuna.search_adzuna_jobs(q="backend", location="United Kingdom"))
    assert len(data["results"]) == 1
    assert adzuna.get_cached_result("111") is not None

    data = asyncio.run(adzuna.search_adzuna_jobs(q="backend", experience_level_filter="entry"))
    assert data["results"] == []
