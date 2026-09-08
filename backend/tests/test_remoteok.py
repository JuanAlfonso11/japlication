import asyncio

from app.services import remoteok

# The first element of Remote OK's response is a legal notice, not a job.
LEGAL_NOTICE = {
    "legal": "API Terms of Service: Please link back ... and mention Remote OK as a source",
}

SAMPLE = {
    "id": "1137300",
    # Remote OK calls the job title "position" — there is no "title" key.
    "position": "QA Engineer",
    "company": "SunnyData",
    "url": "https://remoteOK.com/remote-jobs/remote-qa-engineer-sunnydata-1137300",
    "apply_url": "https://sunnydata.example.com/careers/qa",
    "location": "Worldwide",
    "tags": ["qa", "testing", "python"],
    "description": "<p>We need a QA engineer with Python experience.</p>",
    "epoch": 1788834930,
    "salary_min": 50000,
    "salary_max": 80000,
}


def _clear_caches():
    remoteok._feed_cache.clear()
    remoteok._search_cache.clear()


def test_normalize_reads_the_title_from_position():
    job = remoteok._normalize(SAMPLE)
    assert job["title"] == "QA Engineer"
    assert job["company"] == "SunnyData"
    assert job["source"] == "remoteok"
    assert job["remoteok_job_id"] == "1137300"


def test_source_url_points_at_remote_ok_not_the_employer():
    """Their terms ask for a link back to the listing on Remote OK, and the
    app's "apply on the original site" button follows source_url — so
    pointing it at apply_url would quietly break the deal that grants
    access."""
    job = remoteok._normalize(SAMPLE)
    assert job["source_url"] == SAMPLE["url"]
    assert job["source_url"] != SAMPLE["apply_url"]


def test_tags_become_skills():
    job = remoteok._normalize(SAMPLE)
    names = {s["name"].lower() for s in job["skills_required"]}
    assert {"qa", "testing", "python"} <= names


def test_salary_is_passed_through_as_usd():
    job = remoteok._normalize(SAMPLE)
    assert job["salary_min"] == 50000
    assert job["salary_max"] == 80000
    assert job["salary_currency"] == "USD"


def test_a_zero_salary_means_not_stated_not_unpaid():
    """Passing 0 through would render as a $0 band on the card."""
    job = remoteok._normalize({**SAMPLE, "salary_min": 0, "salary_max": 0})
    assert job["salary_min"] is None
    assert job["salary_max"] is None
    assert job["salary_currency"] is None


def test_the_epoch_timestamp_becomes_a_date():
    job = remoteok._normalize(SAMPLE)
    assert job["posted_at"] is not None
    assert job["posted_at"].year == 2026


def test_rows_missing_id_position_or_url_are_dropped():
    assert remoteok._normalize({**SAMPLE, "id": None}) is None
    assert remoteok._normalize({**SAMPLE, "position": ""}) is None
    assert remoteok._normalize({**SAMPLE, "url": None}) is None


def test_the_legal_notice_element_is_not_treated_as_a_job():
    assert remoteok._normalize(LEGAL_NOTICE) is None


def _fake_client(payload, status=200, capture=None):
    class FakeResponse:
        status_code = status

        def json(self):
            return payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            if capture is not None:
                capture.update(kwargs.get("headers") or {})
            return FakeResponse()

    return lambda *a, **k: FakeClient()


def test_the_browser_user_agent_is_sent(monkeypatch):
    """Load-bearing, not cosmetic: Cloudflare serves a challenge page to
    anything that looks like a script, which is why this source was passed
    over the first time it was investigated."""
    _clear_caches()
    headers = {}
    monkeypatch.setattr(remoteok.httpx, "AsyncClient", _fake_client([LEGAL_NOTICE, SAMPLE], capture=headers))

    asyncio.run(remoteok.search_remoteok_jobs())
    assert "Mozilla" in headers.get("User-Agent", "")


def test_search_skips_the_legal_notice_and_returns_jobs(monkeypatch):
    _clear_caches()
    monkeypatch.setattr(remoteok.httpx, "AsyncClient", _fake_client([LEGAL_NOTICE, SAMPLE]))

    data = asyncio.run(remoteok.search_remoteok_jobs())
    assert [r["title"] for r in data["results"]] == ["QA Engineer"]


def test_search_filters_by_query(monkeypatch):
    _clear_caches()
    other = {**SAMPLE, "id": "2", "position": "Graphic Designer", "tags": ["figma"],
             "description": "<p>Design things.</p>"}
    monkeypatch.setattr(remoteok.httpx, "AsyncClient", _fake_client([LEGAL_NOTICE, SAMPLE, other]))

    data = asyncio.run(remoteok.search_remoteok_jobs(q="testing"))
    assert [r["title"] for r in data["results"]] == ["QA Engineer"]


def test_a_non_200_becomes_a_clean_provider_error(monkeypatch):
    _clear_caches()
    monkeypatch.setattr(remoteok.httpx, "AsyncClient", _fake_client([], status=403))

    try:
        asyncio.run(remoteok.search_remoteok_jobs())
        raise AssertionError("deberia haber lanzado RemoteOkError")
    except remoteok.RemoteOkError as exc:
        assert "403" in str(exc)


def test_results_are_retrievable_from_the_cache_afterwards(monkeypatch):
    _clear_caches()
    monkeypatch.setattr(remoteok.httpx, "AsyncClient", _fake_client([LEGAL_NOTICE, SAMPLE]))

    data = asyncio.run(remoteok.search_remoteok_jobs())
    job_id = data["results"][0]["remoteok_job_id"]
    assert remoteok.get_cached_result(job_id)["title"] == "QA Engineer"
