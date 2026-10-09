import asyncio

from app.services import aijobs
from app.services.external_jobs.registry import PROVIDERS, normalize_results

# Forma real de un resultado de GET /api/jobs (2026-10-08).
SAMPLE_RAW = {
    "title": "Backend Software Engineer - Python/Postgres [Remote / Global]",
    "company": "Enveritas",
    "location": "Global - Remote Work",
    "remote": True,
    "category": "Engineering",
    "level": "Mid",
    "region": "Other",
    "salary": "$162K - $180K  Offers Equity",
    "posted": "2026-10-07",
    "url": "https://artificialintelligencejobs.co/jobs/enveritas-backend-software-engineer-python-93106b8e",
    "apply_url": "https://job-boards.greenhouse.io/enveritas/jobs/4006514008",
}
SAMPLE_ID = "enveritas-backend-software-engineer-python-93106b8e"


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

    monkeypatch.setattr(aijobs.httpx, "AsyncClient", FakeAsyncClient)


def test_normalize_maps_core_fields():
    job = aijobs._normalize(SAMPLE_RAW)
    assert job["aijobs_job_id"] == SAMPLE_ID
    assert job["source"] == "aijobs"
    assert job["source_url"] == SAMPLE_RAW["url"]  # atribucion: siempre su ficha
    assert job["apply_url"] == SAMPLE_RAW["apply_url"]
    assert job["apply_ats"] == "greenhouse"
    assert job["remote_type"] == "remote"
    assert job["seniority"] == "mid"
    assert (job["salary_min"], job["salary_max"], job["salary_currency"]) == (162000, 180000, "USD")
    assert job["posted_at"].isoformat().startswith("2026-10-07")
    # Sin descripcion en la API: se arma con lo que si trae, y lo dice.
    assert "Enveritas" in job["description"] and "open the posting" in job["description"]


def test_levels_and_work_mode():
    assert aijobs._normalize({**SAMPLE_RAW, "level": "Lead+"})["seniority"] == "lead"
    assert aijobs._normalize({**SAMPLE_RAW, "level": "Entry"})["seniority"] == "entry"
    onsite = aijobs._normalize({**SAMPLE_RAW, "remote": False, "location": "London"})
    assert onsite["remote_type"] == "onsite"
    hybrid = aijobs._normalize({**SAMPLE_RAW, "remote": False, "location": "Austin, TX (Hybrid)"})
    assert hybrid["remote_type"] == "hybrid"


def test_parse_salary_only_when_unambiguous():
    assert aijobs.parse_salary("CA$115K - CA$140K") == (115000, 140000, "CAD")
    assert aijobs.parse_salary("$240K") == (240000, 240000, "USD")
    assert aijobs.parse_salary("£80K - £95K") == (80000, 95000, "GBP")
    assert aijobs.parse_salary("$50 - $70") == (None, None, None)  # por hora, no anual
    assert aijobs.parse_salary("$100K - €90K") == (None, None, None)  # monedas mezcladas
    assert aijobs.parse_salary(None) == (None, None, None)
    assert aijobs.parse_salary("Competitive") == (None, None, None)


def test_job_id_is_the_url_slug():
    assert aijobs._job_id(SAMPLE_RAW["url"] + "/") == SAMPLE_ID
    assert aijobs._job_id(None) is None


def test_search_maps_filters_and_pagination(monkeypatch):
    calls = []
    _fake_client(monkeypatch, {"jobs": [], "matched": 0}, calls)
    asyncio.run(aijobs.search_aijobs_jobs(
        q="python", experience_level_filter="lead", remote_type_filter="remote", page=3,
    ))
    assert calls[-1] == {"limit": 100, "q": "python", "remote": "true", "level": "Lead+", "offset": 200}


def test_location_filters_locally_except_when_remote(monkeypatch):
    london = {**SAMPLE_RAW, "remote": False, "location": "London", "url": SAMPLE_RAW["url"] + "-ldn"}
    paris = {**SAMPLE_RAW, "remote": False, "location": "Paris", "url": SAMPLE_RAW["url"] + "-par"}
    calls = []
    _fake_client(monkeypatch, {"jobs": [london, paris, SAMPLE_RAW], "matched": 3}, calls)

    data = asyncio.run(aijobs.search_aijobs_jobs(location="london"))
    assert [j["location"] for j in data["results"]] == ["London"]
    assert "city" not in calls[-1] and "region" not in calls[-1]

    data = asyncio.run(aijobs.search_aijobs_jobs(location="Dominican Republic", remote_type_filter="remote"))
    assert [j["remote_type"] for j in data["results"]] == ["remote"]


def test_has_more_uses_matched(monkeypatch):
    _fake_client(monkeypatch, {"jobs": [SAMPLE_RAW], "matched": 250})
    assert asyncio.run(aijobs.search_aijobs_jobs())["has_more"] is True
    _fake_client(monkeypatch, {"jobs": [SAMPLE_RAW], "matched": 1})
    assert asyncio.run(aijobs.search_aijobs_jobs())["has_more"] is False


def test_search_raises_its_own_error_on_bad_status(monkeypatch):
    _fake_client(monkeypatch, None, status_code=404)
    try:
        asyncio.run(aijobs.search_aijobs_jobs(q="x"))
    except aijobs.AIJobsError:
        pass
    else:
        assert False, "expected AIJobsError"


def test_registry_normalizes_id_for_import(monkeypatch):
    _fake_client(monkeypatch, {"jobs": [SAMPLE_RAW], "matched": 1})
    aijobs._search_cache.clear()
    spec = PROVIDERS["aijobs"]
    assert spec.no_auth is True
    out = asyncio.run(aijobs.search_aijobs_jobs())
    [norm] = normalize_results(spec, out["results"])
    assert norm["external_id"] == SAMPLE_ID
    assert spec.get_cached(SAMPLE_ID)["company"] == "Enveritas"
