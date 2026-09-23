import asyncio

from app.services import web3career

# Shape copied from a live response (2026-09-23), trimmed.
SAMPLE_JOB = {
    "id": 154500,
    "date": "Tue, 22 Sep 2026 20:04:13 +0100",
    "date_epoch": 1790103853,
    "is_remote": True,
    "country": "remote",
    "city": "remote",
    "title": "Senior Frontend Engineer",
    "company": "Solana Foundation",
    "location": " Remote ",
    "apply_url": "https://web3.career/r/wATN0UTM__QnLimt",
    "tags": ["engineer", "remote", "react", "solana"],
    "salary_min_value": "110400.0",
    "salary_max_value": None,
    "salary_currency": "USD",
    "salary_unit": None,
    "estimated_min_salary": 200000,
    "estimated_max_salary": 300000,
    "estimated_avg_salary": 250000,
    "description": "<p>We need a senior frontend engineer.</p>",
}
SAMPLE_RESPONSE = ["Web3 Jobs API https://web3.career", "URL params: ...", [SAMPLE_JOB]]


def test_normalize_keeps_apply_url_untouched_and_real_salary_only():
    job = web3career._normalize(SAMPLE_JOB)
    # Their terms: link back through apply_url, unmodified.
    assert job["source_url"] == SAMPLE_JOB["apply_url"]
    assert job["web3career_job_id"] == "154500"
    assert job["location"] == "Remote"
    assert job["remote_type"] == "remote"
    assert job["salary_min"] == 110400.0
    assert job["salary_max"] is None  # the estimate is not the employer's number
    assert job["posted_at"].year == 2026


def test_query_and_location_become_slugs():
    assert web3career._tag(" Smart Contracts ") == "smart-contracts"
    assert web3career._tag(None) is None
    assert web3career._country("United States") == "united-states"
    assert web3career._country("Remote") is None


def test_search_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(web3career.settings, "WEB3CAREER_TOKEN", None)
    try:
        asyncio.run(web3career.search_web3career_jobs(q="react"))
        assert False, "expected Web3CareerError"
    except web3career.Web3CareerError:
        pass


def test_search_sends_tag_and_remote(monkeypatch):
    monkeypatch.setattr(web3career.settings, "WEB3CAREER_TOKEN", "tok")
    seen = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return SAMPLE_RESPONSE

    async def fake_get(provider, url, params=None, **kw):
        seen.update(params)
        return FakeResponse()

    monkeypatch.setattr(web3career.external_http, "get", fake_get)
    web3career._response_cache.clear()
    web3career._search_cache.clear()

    data = asyncio.run(web3career.search_web3career_jobs(q="React", remote_type_filter="remote"))
    assert seen["tag"] == "react" and seen["remote"] == "true" and seen["token"] == "tok"
    assert len(data["results"]) == 1
    assert web3career.get_cached_result("154500") is not None


def test_bad_token_html_page_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(web3career.settings, "WEB3CAREER_TOKEN", "bad")

    class HtmlResponse:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    async def fake_get(*a, **k):
        return HtmlResponse()

    monkeypatch.setattr(web3career.external_http, "get", fake_get)
    web3career._response_cache.clear()
    try:
        asyncio.run(web3career.search_web3career_jobs(q="rust"))
        assert False, "expected Web3CareerError"
    except web3career.Web3CareerError as exc:
        assert "WEB3CAREER_TOKEN" in str(exc)
