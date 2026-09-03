import asyncio
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.config import settings
from app.services import upwork

SAMPLE_NODE_FIXED = {
    "id": "gid-1",
    "ciphertext": "~01abc",
    "title": "Build a Django admin dashboard",
    "description": "Client needs a Django admin dashboard.\n\nRequirements:\n- Python\n- Django\n- PostgreSQL",
    "experienceLevel": "EXPERT",
    "publishedDateTime": "2024-05-01T12:00:00Z",
    "category": "Web Development",
    "skills": [{"name": "Python"}, {"name": "Django"}],
    "amount": {"rawValue": "1500", "currency": "USD"},
    "hourlyBudgetMin": None,
    "hourlyBudgetMax": None,
    "client": {"companyName": "Acme Freelance Client", "location": {"country": "United States"}},
}

SAMPLE_NODE_HOURLY = {
    "id": "gid-2",
    "ciphertext": "~02def",
    "title": "Ongoing React support",
    "description": "Need ongoing React support.",
    "skills": [{"name": "React"}],
    "hourlyBudgetMin": {"rawValue": "40", "currency": "USD"},
    "hourlyBudgetMax": {"rawValue": "70", "currency": "USD"},
    "client": {"companyName": "Beta Client", "location": {}},
}


def test_get_authorization_url_includes_client_id_and_state(monkeypatch):
    monkeypatch.setattr(settings, "UPWORK_CLIENT_ID", "client-123")
    monkeypatch.setattr(settings, "UPWORK_CLIENT_SECRET", "secret-456")
    url = upwork.get_authorization_url("state-token-xyz")
    parsed = urlparse(url)
    assert parsed.netloc == "www.upwork.com"
    qs = parse_qs(parsed.query)
    assert qs["client_id"] == ["client-123"]
    assert qs["state"] == ["state-token-xyz"]
    assert qs["response_type"] == ["code"]


def test_get_authorization_url_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "UPWORK_CLIENT_ID", None)
    monkeypatch.setattr(settings, "UPWORK_CLIENT_SECRET", None)
    with pytest.raises(upwork.UpworkNotConfigured):
        upwork.get_authorization_url("state")


def test_build_filter_maps_query_and_skills():
    assert upwork._build_filter("django developer", None) == {"titleExpression_eq": "django developer"}
    assert upwork._build_filter(None, ["Python", "Django"]) == {"skillExpression_eq": "Python OR Django"}
    assert upwork._build_filter(None, None) == {}


def test_normalize_fixed_price_project():
    normalized = upwork._normalize(SAMPLE_NODE_FIXED)
    assert normalized["upwork_job_id"] == "~01abc"
    assert normalized["source"] == "upwork"
    assert normalized["source_url"] == "https://www.upwork.com/jobs/~01abc"
    assert normalized["company"] == "Acme Freelance Client"
    assert normalized["employment_type"] == "contract"
    assert normalized["remote_type"] == "remote"
    assert normalized["is_hourly"] is False
    assert normalized["salary_min"] == normalized["salary_max"] == 1500.0
    assert normalized["salary_currency"] == "USD"
    assert "precio fijo" in normalized["description"].lower()

    skill_names = {s["name"] for s in normalized["skills_required"]}
    assert {"Python", "Django"} <= skill_names
    # PostgreSQL is in the description text but not the structured `skills` list.
    assert "PostgreSQL" in skill_names


def test_normalize_hourly_project():
    normalized = upwork._normalize(SAMPLE_NODE_HOURLY)
    assert normalized["is_hourly"] is True
    assert normalized["salary_min"] == 40.0
    assert normalized["salary_max"] == 70.0
    assert "hora" in normalized["description"].lower()


def test_normalize_published_date_parsed():
    normalized = upwork._normalize(SAMPLE_NODE_FIXED)
    assert normalized["posted_at"] == datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)


def test_extract_token_fields_with_expiry():
    fields = upwork._extract_token_fields(
        {"access_token": "tok", "refresh_token": "ref", "token_type": "Bearer", "expires_in": 3600}
    )
    assert fields["access_token"] == "tok"
    assert fields["refresh_token"] == "ref"
    assert fields["expires_at"] is not None
    delta = fields["expires_at"] - datetime.now(timezone.utc)
    assert 3500 < delta.total_seconds() < 3700


def test_extract_token_fields_without_access_token_raises():
    with pytest.raises(upwork.UpworkError):
        upwork._extract_token_fields({"token_type": "Bearer"})


def test_search_upwork_jobs_populates_cache(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "data": {
                    "marketplaceJobPostings": {
                        "edges": [{"node": SAMPLE_NODE_FIXED}],
                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                    }
                }
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            assert headers["Authorization"] == "Bearer test-access-token"
            return FakeResponse()

    monkeypatch.setattr(upwork.httpx, "AsyncClient", FakeAsyncClient)
    upwork._search_cache.clear()

    data = asyncio.run(upwork.search_upwork_jobs("test-access-token", q="django"))

    assert len(data["results"]) == 1
    assert data["has_more"] is True
    assert upwork.get_cached_result("~01abc") is not None


def test_search_upwork_jobs_raises_permission_error_on_401(monkeypatch):
    class FakeResponse:
        status_code = 401
        text = "unauthorized"

        def json(self):
            return {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            return FakeResponse()

    monkeypatch.setattr(upwork.httpx, "AsyncClient", FakeAsyncClient)
    with pytest.raises(PermissionError):
        asyncio.run(upwork.search_upwork_jobs("expired-token", q="django"))


def test_get_cached_result_expires_after_ttl():
    upwork._search_cache["stale"] = {
        "cached_at": time.time() - upwork._CACHE_TTL_SECONDS - 1,
        "job": {"title": "Stale"},
    }
    assert upwork.get_cached_result("stale") is None
    assert "stale" not in upwork._search_cache
