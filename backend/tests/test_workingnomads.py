import asyncio

from app.services import workingnomads

SAMPLE = {
    "url": "https://www.workingnomads.com/job/go/1843255/",
    "title": "Senior Data Engineer (Azure)",
    "company_name": "Proxify",
    "category_name": "Development",
    "location": "Time zone: CET (+/- 3 hours)",
    # Comma-separated string, not a list — the shape their API actually
    # returns, which is easy to mistake for a JSON array.
    "tags": "azure,sql,python",
    "description": "<p>We need a senior data engineer with Azure and SQL experience.</p>",
    "pub_date": "2026-09-07T14:44:23-04:00",
}


def _clear_caches():
    workingnomads._feed_cache.clear()
    workingnomads._search_cache.clear()


def test_normalize_maps_the_fields_the_app_needs():
    job = workingnomads._normalize(SAMPLE)
    assert job["title"] == "Senior Data Engineer (Azure)"
    assert job["company"] == "Proxify"
    assert job["source"] == "workingnomads"
    assert job["source_url"] == SAMPLE["url"]
    assert job["workingnomads_job_id"] == SAMPLE["url"]
    assert job["remote_type"] == "remote"
    assert job["posted_at"] is not None


def test_comma_separated_tags_become_skills():
    job = workingnomads._normalize(SAMPLE)
    names = {s["name"].lower() for s in job["skills_required"]}
    assert {"azure", "sql", "python"} <= names


def test_tags_are_not_duplicated_when_the_body_already_mentions_them():
    job = workingnomads._normalize(SAMPLE)
    names = [s["name"].lower() for s in job["skills_required"]]
    assert len(names) == len(set(names))


def test_html_in_the_description_is_stripped():
    job = workingnomads._normalize(SAMPLE)
    assert "<p>" not in job["description"]
    assert "senior data engineer" in job["description"].lower()


def test_rows_without_a_url_or_title_are_dropped():
    """No URL means nothing to apply to; no title means an unusable card."""
    assert workingnomads._normalize({**SAMPLE, "url": None}) is None
    assert workingnomads._normalize({**SAMPLE, "title": ""}) is None


def test_a_missing_location_falls_back_to_remote():
    job = workingnomads._normalize({**SAMPLE, "location": None})
    assert job["location"] == "Remote"


def test_a_malformed_date_does_not_break_the_row():
    job = workingnomads._normalize({**SAMPLE, "pub_date": "no es una fecha"})
    assert job is not None
    assert job["posted_at"] is None


def _fake_client(payload, status=200):
    class FakeResponse:
        status_code = status

        def json(self):
            if isinstance(payload, Exception):
                raise payload
            return payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return FakeResponse()

    return lambda *a, **k: FakeClient()


def test_search_filters_by_query(monkeypatch):
    _clear_caches()
    other = {**SAMPLE, "url": "https://www.workingnomads.com/job/go/2/", "title": "Graphic Designer",
             "tags": "figma", "description": "<p>Design things.</p>"}
    monkeypatch.setattr(workingnomads.httpx, "AsyncClient", _fake_client([SAMPLE, other]))

    data = asyncio.run(workingnomads.search_workingnomads_jobs(q="azure"))
    assert [r["title"] for r in data["results"]] == ["Senior Data Engineer (Azure)"]


def test_search_excludes_the_whole_provider_for_onsite(monkeypatch):
    """Everything here is remote by definition, so asking for onsite must
    return nothing rather than remote jobs that don't match the filter."""
    _clear_caches()
    monkeypatch.setattr(workingnomads.httpx, "AsyncClient", _fake_client([SAMPLE]))

    data = asyncio.run(workingnomads.search_workingnomads_jobs(remote_type_filter="onsite"))
    assert data["results"] == []


def test_a_non_200_becomes_a_clean_provider_error(monkeypatch):
    """The aggregate fan-out reports this per-source instead of failing the
    whole search — so it has to be a typed error, not a raw exception."""
    _clear_caches()
    monkeypatch.setattr(workingnomads.httpx, "AsyncClient", _fake_client([], status=503))

    try:
        asyncio.run(workingnomads.search_workingnomads_jobs())
        raise AssertionError("deberia haber lanzado WorkingNomadsError")
    except workingnomads.WorkingNomadsError as exc:
        assert "503" in str(exc)


def test_an_unexpected_payload_shape_is_rejected(monkeypatch):
    _clear_caches()
    monkeypatch.setattr(workingnomads.httpx, "AsyncClient", _fake_client({"jobs": []}))

    try:
        asyncio.run(workingnomads.search_workingnomads_jobs())
        raise AssertionError("deberia haber lanzado WorkingNomadsError")
    except workingnomads.WorkingNomadsError:
        pass


def test_results_are_retrievable_from_the_cache_afterwards(monkeypatch):
    """The import flow looks the posting up by id after the search, so a
    result that can't be found again can't be added to the queue."""
    _clear_caches()
    monkeypatch.setattr(workingnomads.httpx, "AsyncClient", _fake_client([SAMPLE]))

    data = asyncio.run(workingnomads.search_workingnomads_jobs())
    job_id = data["results"][0]["workingnomads_job_id"]
    assert workingnomads.get_cached_result(job_id)["title"] == SAMPLE["title"]
