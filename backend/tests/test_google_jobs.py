import asyncio
import time
from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.services import google_jobs

SAMPLE_RAW_RESULT = {
    "job_id": "abc123",
    "title": "Backend Engineer",
    "company_name": "Rivergate Labs",
    "location": "Remote",
    "via": "via LinkedIn",
    "description": (
        "Rivergate Labs is hiring a Backend Engineer with 3+ years of experience.\n\n"
        "Requirements:\n- Python\n- PostgreSQL\n- Docker\n\n"
        "Nice to have:\n- Kubernetes\n"
    ),
    "extensions": ["2 days ago", "Full-time"],
    "detected_extensions": {
        "posted_at": "2 days ago",
        "schedule_type": "Full-time",
        "salary": "$110K–$140K a year",
        "work_from_home": True,
    },
    "apply_options": [
        {"title": "Company site", "link": "https://rivergatelabs.example/careers/backend-engineer"},
        {"title": "LinkedIn", "link": "https://linkedin.com/jobs/view/123"},
    ],
    "thumbnail": "https://example.com/logo.png",
}


def test_normalize_maps_core_fields_and_reuses_heuristic_extraction():
    normalized = google_jobs._normalize(SAMPLE_RAW_RESULT)

    assert normalized["google_job_id"] == "abc123"
    assert normalized["source"] == "google_jobs"
    assert normalized["title"] == "Backend Engineer"
    assert normalized["company"] == "Rivergate Labs"
    # First apply option (with a link) wins as the canonical source_url.
    assert normalized["source_url"] == "https://rivergatelabs.example/careers/backend-engineer"
    assert len(normalized["apply_options"]) == 2

    skill_names = {s["name"] for s in normalized["skills_required"]}
    assert "Python" in skill_names
    assert "PostgreSQL" in skill_names
    assert "Docker" in skill_names
    # "Kubernetes" sits under the "Nice to have" section of the description.
    kubernetes_entries = [s for s in normalized["skills_required"] if s["name"] == "Kubernetes"]
    assert kubernetes_entries and kubernetes_entries[0]["importance"] == "nice_to_have"


def test_normalize_prefers_detected_extensions_for_remote_and_schedule():
    normalized = google_jobs._normalize(SAMPLE_RAW_RESULT)
    assert normalized["remote_type"] == "remote"  # detected_extensions.work_from_home
    assert normalized["employment_type"] == "full_time"  # detected_extensions.schedule_type


def test_normalize_falls_back_to_share_link_when_no_apply_options():
    raw = dict(SAMPLE_RAW_RESULT, apply_options=[], share_link="https://google.com/jobs/abc123")
    normalized = google_jobs._normalize(raw)
    assert normalized["source_url"] == "https://google.com/jobs/abc123"


def test_parse_salary_handles_k_suffix_and_range():
    lo, hi, currency = google_jobs._parse_salary({"salary": "$110K–$140K a year"})
    assert lo == 110_000
    assert hi == 140_000
    assert currency == "USD"


def test_parse_salary_handles_single_value():
    lo, hi, currency = google_jobs._parse_salary({"salary": "€65K a year"})
    assert lo == hi == 65_000
    assert currency == "EUR"


def test_parse_salary_returns_none_when_absent():
    assert google_jobs._parse_salary({}) == (None, None, None)


def test_parse_relative_posted_at_days_ago():
    result = google_jobs._parse_relative_posted_at("2 days ago")
    assert result is not None
    delta = datetime.now(timezone.utc) - result
    assert 1.5 * 86400 < delta.total_seconds() < 2.5 * 86400


def test_parse_relative_posted_at_unrecognized_text_returns_none():
    assert google_jobs._parse_relative_posted_at("Just posted") is None
    assert google_jobs._parse_relative_posted_at(None) is None


def test_search_raises_clean_error_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", None)
    with pytest.raises(google_jobs.GoogleJobsError, match="SERPAPI_API_KEY"):
        asyncio.run(google_jobs.search_google_jobs(q="backend engineer"))


def test_search_populates_cache_and_returns_pagination(monkeypatch):
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", "test-key")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "jobs_results": [SAMPLE_RAW_RESULT],
                "serpapi_pagination": {"next_page_token": "next-token-xyz"},
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            assert params["engine"] == "google_jobs"
            assert params["api_key"] == "test-key"
            return FakeResponse()

    monkeypatch.setattr(google_jobs.httpx, "AsyncClient", FakeAsyncClient)
    google_jobs._search_cache.clear()

    data = asyncio.run(google_jobs.search_google_jobs(q="backend engineer", location="Remote"))

    assert data["next_page_token"] == "next-token-xyz"
    assert len(data["results"]) == 1
    assert data["results"][0]["google_job_id"] == "abc123"
    assert google_jobs.get_cached_result("abc123") is not None


def test_get_cached_result_expires_after_ttl():
    google_jobs._search_cache["stale-id"] = {
        "cached_at": time.time() - google_jobs._CACHE_TTL_SECONDS - 1,
        "job": {"title": "Stale"},
    }
    assert google_jobs.get_cached_result("stale-id") is None
    assert "stale-id" not in google_jobs._search_cache


def test_get_cached_result_missing_id_returns_none():
    assert google_jobs.get_cached_result("does-not-exist") is None
