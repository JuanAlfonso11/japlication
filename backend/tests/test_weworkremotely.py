import asyncio
from xml.etree import ElementTree

from app.services import weworkremotely

SAMPLE_ITEM_XML = """
<item>
  <title>Acme Corp: Senior Backend Engineer</title>
  <region>Worldwide</region>
  <country></country>
  <type>Full-Time</type>
  <description><![CDATA[<p>We need a Senior Backend Engineer with Python and Docker experience.</p>]]></description>
  <pubDate>Mon, 01 Sep 2026 12:00:00 +0000</pubDate>
  <guid>https://weworkremotely.com/remote-jobs/acme-corp-senior-backend-engineer</guid>
</item>
"""

SAMPLE_FEED_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>We Work Remotely</title>
    {SAMPLE_ITEM_XML}
  </channel>
</rss>
"""


def test_normalize_splits_company_and_title_on_colon():
    item = ElementTree.fromstring(SAMPLE_ITEM_XML)
    normalized = weworkremotely._normalize(item)
    assert normalized["company"] == "Acme Corp"
    assert normalized["title"] == "Senior Backend Engineer"
    assert normalized["source"] == "weworkremotely"
    assert normalized["remote_type"] == "remote"
    assert normalized["wwr_job_id"] == "acme-corp-senior-backend-engineer"
    assert normalized["employment_type"] == "full_time"


def test_normalize_skips_items_without_guid_or_title():
    item = ElementTree.fromstring("<item><region>Worldwide</region></item>")
    assert weworkremotely._normalize(item) is None


def test_search_fetches_and_filters(monkeypatch):
    class FakeResponse:
        status_code = 200
        content = SAMPLE_FEED_XML.encode()

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(weworkremotely.httpx, "AsyncClient", FakeAsyncClient)
    weworkremotely._feed_cache.clear()
    weworkremotely._search_cache.clear()

    data = asyncio.run(weworkremotely.search_weworkremotely_jobs(q="backend"))
    assert len(data["results"]) == 1
    assert weworkremotely.get_cached_result("acme-corp-senior-backend-engineer") is not None

    data = asyncio.run(weworkremotely.search_weworkremotely_jobs(q="frontend"))
    assert data["results"] == []
