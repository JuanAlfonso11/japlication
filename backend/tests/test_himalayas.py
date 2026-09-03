import asyncio
import time
from datetime import datetime, timezone

from app.services import himalayas

SAMPLE_RAW_JOB = {
    "guid": "hj-001",
    "title": "Senior React Engineer",
    "companyName": "Northbeam",
    "companySlug": "northbeam",
    "companyLogo": "https://example.com/logo.png",
    "employmentType": "Full Time",
    "minSalary": 90000,
    "maxSalary": 120000,
    "salaryPeriod": "annual",
    "currency": "USD",
    "seniority": ["Senior"],
    "locationRestrictions": ["United States", "Canada"],
    "timezoneRestrictions": [-5, -8],
    "categories": ["React", "Frontend"],
    "parentCategories": ["Developer"],
    "description": (
        "<p>Northbeam is hiring a Senior React Engineer.</p>"
        "<h3>Requirements</h3><ul><li>5+ years with React</li><li>TypeScript</li></ul>"
    ),
    "excerpt": "Northbeam is hiring a Senior React Engineer.",
    "pubDate": 1700000000,
    "expiryDate": 1705000000,
    "applicationLink": "https://northbeam.example/careers/senior-react-engineer",
}


def test_normalize_maps_core_fields():
    normalized = himalayas._normalize(SAMPLE_RAW_JOB)
    assert normalized["himalayas_job_id"] == "hj-001"
    assert normalized["source"] == "himalayas"
    assert normalized["title"] == "Senior React Engineer"
    assert normalized["company"] == "Northbeam"
    assert normalized["source_url"] == "https://northbeam.example/careers/senior-react-engineer"
    assert normalized["remote_type"] == "remote"
    assert normalized["employment_type"] == "full_time"
    assert normalized["location"] == "United States, Canada"
    assert normalized["salary_min"] == 90000
    assert normalized["salary_max"] == 120000
    assert normalized["salary_currency"] == "USD"


def test_normalize_extracts_skills_from_html_description():
    normalized = himalayas._normalize(SAMPLE_RAW_JOB)
    skill_names = {s["name"] for s in normalized["skills_required"]}
    assert "React" in skill_names
    assert "TypeScript" in skill_names


def test_normalize_adds_categories_as_extra_nice_to_have_skills():
    normalized = himalayas._normalize(SAMPLE_RAW_JOB)
    extras = {s["name"]: s["importance"] for s in normalized["skills_required"]}
    # "Frontend"/"Developer" aren't in the free-text scan but come from Himalayas' own categories.
    assert extras.get("Frontend") == "nice_to_have"


def test_normalize_worldwide_default_location_when_no_restrictions():
    raw = dict(SAMPLE_RAW_JOB, locationRestrictions=[])
    normalized = himalayas._normalize(raw)
    assert normalized["location"] == "Worldwide (remoto)"


def test_normalize_converts_pub_date_to_utc_datetime():
    normalized = himalayas._normalize(SAMPLE_RAW_JOB)
    assert normalized["posted_at"] == datetime.fromtimestamp(1700000000, tz=timezone.utc)


def test_normalize_falls_back_to_excerpt_when_no_description():
    raw = dict(SAMPLE_RAW_JOB, description="")
    normalized = himalayas._normalize(raw)
    assert "Senior React Engineer" in normalized["description"]


def test_search_populates_cache(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"jobs": [SAMPLE_RAW_JOB], "totalCount": 1}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            assert params["page"] == 1
            return FakeResponse()

    monkeypatch.setattr(himalayas.httpx, "AsyncClient", FakeAsyncClient)
    himalayas._search_cache.clear()

    data = asyncio.run(himalayas.search_himalayas_jobs(q="react engineer"))

    assert len(data["results"]) == 1
    assert data["total_count"] == 1
    assert himalayas.get_cached_result("hj-001") is not None


def test_get_cached_result_expires_after_ttl():
    himalayas._search_cache["stale"] = {
        "cached_at": time.time() - himalayas._CACHE_TTL_SECONDS - 1,
        "job": {"title": "Stale"},
    }
    assert himalayas.get_cached_result("stale") is None
    assert "stale" not in himalayas._search_cache
