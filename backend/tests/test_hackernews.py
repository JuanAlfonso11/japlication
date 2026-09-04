import asyncio

from app.services import hackernews

SAMPLE_COMMENT = {
    "id": 12345,
    "author": "acme_hr",
    "created_at": "2026-09-01T15:03:00.000Z",
    "text": (
        "Acme Corp | Senior Backend Engineer | Remote (US) | Full-time | $150k-$180k"
        "<p>We need a Senior Backend Engineer with Python and Docker experience."
    ),
    "children": [],
}

SAMPLE_SEARCH_HIT = {"objectID": "999", "title": "Ask HN: Who is hiring? (September 2026)"}

SAMPLE_THREAD = {
    "id": 999,
    "children": [SAMPLE_COMMENT, {"id": 2, "text": None}, {"id": 3, "dead": True, "text": "hidden"}],
}


def test_parse_posting_splits_pipe_delimited_header():
    normalized = hackernews._parse_posting(SAMPLE_COMMENT)
    assert normalized["company"] == "Acme Corp"
    assert normalized["title"] == "Senior Backend Engineer"
    assert normalized["location"] == "Remote (US)"
    assert normalized["hn_job_id"] == "12345"
    assert normalized["source"] == "hackernews"
    assert normalized["source_url"] == "https://news.ycombinator.com/item?id=12345"


def test_parse_posting_skips_empty_or_missing_text():
    assert hackernews._parse_posting({"id": 1, "text": None}) is None
    assert hackernews._parse_posting({"id": None, "text": "hi"}) is None


def test_search_finds_thread_and_filters(monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            if "search_by_date" in url:
                return FakeResponse({"hits": [SAMPLE_SEARCH_HIT]})
            return FakeResponse(SAMPLE_THREAD)

    monkeypatch.setattr(hackernews.httpx, "AsyncClient", FakeAsyncClient)
    hackernews._thread_cache.clear()
    hackernews._search_cache.clear()

    data = asyncio.run(hackernews.search_hackernews_jobs(q="backend"))
    assert len(data["results"]) == 1
    assert hackernews.get_cached_result("12345") is not None

    data = asyncio.run(hackernews.search_hackernews_jobs(q="frontend"))
    assert data["results"] == []
