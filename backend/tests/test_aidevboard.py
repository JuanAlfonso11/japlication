import asyncio

from app.services import aidevboard
from app.services.external_jobs.registry import PROVIDERS, normalize_results

# Forma real de un resultado de GET /api/v1/jobs (2026-10-08), recortada.
SAMPLE_RAW = {
    "id": "c86f5174-eb44-436e-92ad-1d161af54673",
    "title": "Machine Learning Engineer",
    "slug": "machine-learning-engineer-d6cd8dac",
    "description": "We are hiring an ML engineer to build LLM agents with Python and PyTorch.",
    "salary_min": 120000,
    "salary_max": 150000,
    "location": "San Francisco, CA",
    "workplace": "remote",
    "remote_scope": "unknown",
    "job_type": "full-time",
    "experience_level": "junior",
    "tags": ["llm", "agents", "python"],
    "apply_url": "https://jobs.ashbyhq.com/vapi/a3bde43c/application",
    "published_at": "2026-09-12T04:31:34.84Z",
    "created_at": "2026-09-12T13:41:37.448541Z",
    "company_name": "Vapi",
    "company_logo_url": "https://www.google.com/s2/favicons?domain=vapi.ai&sz=128",
    "url": "https://aidevboard.com/job/c86f5174-eb44-436e-92ad-1d161af54673",
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

    monkeypatch.setattr(aidevboard.httpx, "AsyncClient", FakeAsyncClient)


def test_normalize_maps_core_fields_and_direct_apply_link():
    job = aidevboard._normalize(SAMPLE_RAW)
    assert job["aidevboard_job_id"] == SAMPLE_RAW["id"]
    assert job["source"] == "aidevboard"
    assert job["source_url"] == SAMPLE_RAW["url"]
    # El enlace de postular es el ATS de la empresa, ya identificado.
    assert job["apply_url"] == SAMPLE_RAW["apply_url"]
    assert job["apply_ats"] == "ashby"
    assert job["remote_type"] == "remote"
    assert job["employment_type"] == "full_time"
    assert job["seniority"] == "entry"  # "junior" en su vocabulario
    assert job["salary_min"] == 120000 and job["salary_currency"] == "USD"
    assert job["posted_at"].year == 2026 and job["posted_at"].tzinfo is not None
    assert job["thumbnail"] == SAMPLE_RAW["company_logo_url"]
    assert any(s["name"] == "agents" for s in job["skills_required"])


def test_normalize_levels_and_global_remote():
    assert aidevboard._normalize({**SAMPLE_RAW, "experience_level": "principal"})["seniority"] == "lead"
    assert aidevboard._normalize({**SAMPLE_RAW, "experience_level": "mid"})["seniority"] == "mid"
    job = aidevboard._normalize({**SAMPLE_RAW, "remote_scope": "global"})
    assert job["location"] == "Worldwide (remote)"


def test_normalize_without_salary_has_no_currency():
    job = aidevboard._normalize({**SAMPLE_RAW, "salary_min": None, "salary_max": None})
    assert job["salary_currency"] is None


def test_search_maps_filters_to_their_params(monkeypatch):
    calls = []
    _fake_client(monkeypatch, {"jobs": [], "has_next": False}, calls)
    asyncio.run(aidevboard.search_aidevboard_jobs(
        q="llm", location="United States", experience_level_filter="entry",
        remote_type_filter="onsite", page=2,
    ))
    assert calls[-1] == {
        "limit": 50, "q": "llm", "workplace": "onsite",
        "location": "United States", "level": "junior", "page": 2,
    }


def test_remote_search_does_not_send_location(monkeypatch):
    """En remoto `location` es la sede: mandarla dejaria fuera casi todo."""
    calls = []
    _fake_client(monkeypatch, {"jobs": []}, calls)
    asyncio.run(aidevboard.search_aidevboard_jobs(location="Dominican Republic", remote_type_filter="remote"))
    assert "location" not in calls[-1]
    assert calls[-1]["workplace"] == "remote"


def test_internship_filter_is_not_sent_as_junior(monkeypatch):
    calls = []
    _fake_client(monkeypatch, {"jobs": [SAMPLE_RAW]}, calls)
    data = asyncio.run(aidevboard.search_aidevboard_jobs(experience_level_filter="internship"))
    assert "level" not in calls[-1]
    assert data["results"] == []  # un junior no es una practica


def test_search_caches_results_and_reports_has_more(monkeypatch):
    _fake_client(monkeypatch, {"jobs": [SAMPLE_RAW], "has_next": True})
    aidevboard._search_cache.clear()
    data = asyncio.run(aidevboard.search_aidevboard_jobs(q="ml"))
    assert len(data["results"]) == 1
    assert data["has_more"] is True
    assert aidevboard.get_cached_result(SAMPLE_RAW["id"])["title"] == "Machine Learning Engineer"


def test_search_raises_its_own_error_on_bad_status(monkeypatch):
    _fake_client(monkeypatch, {}, status_code=404)
    try:
        asyncio.run(aidevboard.search_aidevboard_jobs(q="ml"))
    except aidevboard.AIDevBoardError:
        pass
    else:
        assert False, "expected AIDevBoardError"


def test_registry_normalizes_id_for_import(monkeypatch):
    _fake_client(monkeypatch, {"jobs": [SAMPLE_RAW]})
    spec = PROVIDERS["aidevboard"]
    assert spec.no_auth is True
    out = asyncio.run(aidevboard.search_aidevboard_jobs())
    [norm] = normalize_results(spec, out["results"])
    assert norm["external_id"] == SAMPLE_RAW["id"]
    assert "aidevboard_job_id" not in norm
    assert spec.get_cached(SAMPLE_RAW["id"]) is not None
