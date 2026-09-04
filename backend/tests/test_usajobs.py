import asyncio

from app.services import usajobs

SAMPLE_ITEM = {
    "MatchedObjectId": "abc123",
    "MatchedObjectDescriptor": {
        "PositionID": "DE-12345",
        "PositionTitle": "Senior Data Analyst",
        "OrganizationName": "Department of Example",
        "PositionLocationDisplay": "Washington, DC",
        "PositionURI": "https://www.usajobs.gov/job/12345",
        "PublicationStartDate": "2026-09-01T00:00:00.000Z",
        "PositionSchedule": [{"Name": "Full-time"}],
        "PositionRemuneration": [{"MinimumRange": "90000", "MaximumRange": "120000"}],
        "UserArea": {
            "Details": {
                "JobSummary": "We need a Senior Data Analyst with SQL and Python experience.",
                "QualificationSummary": "3+ years of experience required.",
            }
        },
    },
}


def test_is_configured_requires_both_settings(monkeypatch):
    monkeypatch.setattr(usajobs.settings, "USAJOBS_API_KEY", None)
    monkeypatch.setattr(usajobs.settings, "USAJOBS_USER_AGENT", None)
    assert usajobs.is_configured() is False
    monkeypatch.setattr(usajobs.settings, "USAJOBS_API_KEY", "key")
    monkeypatch.setattr(usajobs.settings, "USAJOBS_USER_AGENT", "me@example.com")
    assert usajobs.is_configured() is True


def test_normalize_maps_fields():
    normalized = usajobs._normalize(SAMPLE_ITEM)
    assert normalized["title"] == "Senior Data Analyst"
    assert normalized["company"] == "Department of Example"
    assert normalized["usajobs_job_id"] == "DE-12345"
    assert normalized["source"] == "usajobs"
    assert normalized["employment_type"] == "full_time"
    assert normalized["salary_min"] == 90000.0
    assert normalized["salary_currency"] == "USD"


def test_search_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(usajobs.settings, "USAJOBS_API_KEY", None)
    monkeypatch.setattr(usajobs.settings, "USAJOBS_USER_AGENT", None)
    try:
        asyncio.run(usajobs.search_usajobs_jobs(q="analyst"))
        assert False, "expected USAJobsError"
    except usajobs.USAJobsError:
        pass


def test_search_fetches_and_filters(monkeypatch):
    monkeypatch.setattr(usajobs.settings, "USAJOBS_API_KEY", "key")
    monkeypatch.setattr(usajobs.settings, "USAJOBS_USER_AGENT", "me@example.com")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "SearchResult": {
                    "SearchResultCountAll": 1,
                    "SearchResultItems": [SAMPLE_ITEM],
                }
            }

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, headers=None):
            return FakeResponse()

    monkeypatch.setattr(usajobs.httpx, "AsyncClient", FakeAsyncClient)
    usajobs._search_cache.clear()

    data = asyncio.run(usajobs.search_usajobs_jobs(q="analyst"))
    assert len(data["results"]) == 1
    assert usajobs.get_cached_result("DE-12345") is not None

    data = asyncio.run(usajobs.search_usajobs_jobs(q="analyst", experience_level_filter="entry"))
    assert data["results"] == []
