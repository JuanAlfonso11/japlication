import asyncio

from app.services import freehire
from app.services.external_jobs.registry import PROVIDERS, normalize_results

# Forma real de un resultado de GET /api/v1/jobs/search (2026-10-27), recortada.
SAMPLE_RAW = {
    "public_slug": "backend-engineer-acme-2gha4mke",
    "source": "greenhouse",
    "url": "https://job-boards.greenhouse.io/acme/jobs/123",
    "title": "Backend Engineer",
    "company": "Acme",
    "location": "Remote",
    "description": "<p>Build APIs with Python and PostgreSQL.</p>",
    "regions": ["global"],
    "work_mode": "remote",
    "skills": ["python", "postgresql", "fastapi"],
    "posted_at": "2026-10-28T00:29:44Z",
    "closed_at": None,
    "enrichment": {
        "seniority": "junior",
        "employment_type": "full_time",
        "salary_min": 50000,
        "salary_max": 70000,
        "salary_currency": "USD",
        "requirements": [{"text": "Experience with Python", "priority": "required"}],
    },
    "reality": {"class": "fresh"},
}


def _fake_client(monkeypatch, body, calls=None, status_code=200):
    class FakeResponse:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            return body

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, **kwargs):
            if calls is not None:
                calls.append(dict(params or {}))
            return FakeResponse()

    monkeypatch.setattr(freehire.httpx, "AsyncClient", FakeAsyncClient)


def test_normalize_maps_core_fields_and_original_posting():
    job = freehire._normalize(SAMPLE_RAW)
    assert job["freehire_job_id"] == SAMPLE_RAW["public_slug"]
    assert job["source"] == "freehire"
    assert job["source_url"] == job["apply_url"] == SAMPLE_RAW["url"]
    assert job["apply_ats"] == "greenhouse"
    assert job["remote_type"] == "remote"
    assert job["location"] == "Worldwide (remote)"
    assert job["seniority"] == "entry"
    assert job["employment_type"] == "full_time"
    assert job["salary_min"] == 50000 and job["salary_currency"] == "USD"
    assert job["requirements"] == ["Experience with Python"]
    assert job["description"] == "Build APIs with Python and PostgreSQL."
    assert job["posted_at"].tzinfo is not None
    assert any(s["name"] == "fastapi" for s in job["skills_required"])


def test_unlabeled_seniority_is_inferred_and_no_salary_no_currency():
    raw = {**SAMPLE_RAW, "enrichment": {"salary_currency": "USD"}, "title": "Senior Backend Engineer"}
    job = freehire._normalize(raw)
    assert job["seniority"] == "senior"
    assert job["salary_currency"] is None


def test_search_maps_filters_to_their_params(monkeypatch):
    calls = []
    _fake_client(monkeypatch, {"data": [], "meta": {"total": 0}}, calls)
    asyncio.run(freehire.search_freehire_jobs(
        q="python", location="Dominican Republic", experience_level_filter="entry",
        remote_type_filter="remote", page=3,
    ))
    assert calls[-1] == {
        "limit": 50, "sort": "posted_at", "order": "desc", "reality": "fresh", "q": "python",
        "work_mode": "remote", "seniority": "junior", "seniority_include_unspecified": "true", "offset": 100,
    }


def test_search_skips_closed_caches_and_reports_has_more(monkeypatch):
    cerrada = {**SAMPLE_RAW, "public_slug": "closed-one", "closed_at": "2026-10-01T00:00:00Z"}
    _fake_client(monkeypatch, {"data": [SAMPLE_RAW, cerrada], "meta": {"offset": 0, "total": 300}})
    freehire._search_cache.clear()
    data = asyncio.run(freehire.search_freehire_jobs(q="python"))
    assert [j["freehire_job_id"] for j in data["results"]] == [SAMPLE_RAW["public_slug"]]
    assert data["has_more"] is True
    assert freehire.get_cached_result(SAMPLE_RAW["public_slug"])["title"] == "Backend Engineer"


def test_search_raises_its_own_error_on_bad_status(monkeypatch):
    _fake_client(monkeypatch, {}, status_code=429)
    try:
        asyncio.run(freehire.search_freehire_jobs(q="python"))
    except freehire.FreehireError:
        pass
    else:
        assert False, "expected FreehireError"


def test_registry_normalizes_id_for_import(monkeypatch):
    _fake_client(monkeypatch, {"data": [SAMPLE_RAW], "meta": {"total": 1}})
    spec = PROVIDERS["freehire"]
    assert spec.no_auth is True
    out = asyncio.run(freehire.search_freehire_jobs())
    [norm] = normalize_results(spec, out["results"])
    assert norm["external_id"] == SAMPLE_RAW["public_slug"]
    assert "freehire_job_id" not in norm
