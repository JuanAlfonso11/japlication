"""Tests for LinkedIn search through Bright Data.

The things worth pinning are the ones that fail silently: the remote tag (a
wrong tag just shows the wrong badge) and the cost path (a cache miss that
stalls Discover, or a cache hit that pays again, both still look like "it
works").
"""

import asyncio

import pytest

from app.services import linkedin_jobs

RECORD = {
    "job_posting_id": "4464695781",
    "job_title": "Sitecore Developer (.NET) - Remote work | REF#304190",
    "company_name": "BairesDev",
    "job_location": "Santo Domingo, Distrito Nacional, Dominican Republic",
    "job_summary": "We are looking for a .NET developer with C# and SQL Server experience.",
    "job_employment_type": "Full-time",
    "job_seniority_level": "Entry level",
    "job_posted_date": "2026-09-09T04:28:41.343Z",
    "job_posted_time": "2 days ago",
    "url": "https://www.linkedin.com/jobs/view/sitecore-developer-4464695781?_l=en",
    "apply_link": None,
}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(linkedin_jobs.settings, "BRIGHTDATA_API_KEY", "key")
    monkeypatch.setattr(linkedin_jobs.settings, "BRIGHTDATA_LINKEDIN_LOCATION", "Worldwide")
    for cache in (
        linkedin_jobs._query_cache,
        linkedin_jobs._job_cache,
        linkedin_jobs._failures,
        linkedin_jobs._in_flight,
    ):
        cache.clear()


async def _never_spend(*_args, **_kwargs):
    raise AssertionError("this path must not consume the paid daily budget")


def test_normalize_maps_fields():
    job = linkedin_jobs._normalize(RECORD, "remote")
    assert job["linkedin_job_id"] == "4464695781"
    assert job["source"] == "linkedin"
    assert job["source_url"] == "https://www.linkedin.com/jobs/view/sitecore-developer-4464695781"
    assert job["employment_type"] == "full_time"
    assert job["seniority"] == "entry"
    assert job["posted_at"].year == 2026
    assert job["via"] == "LinkedIn"


def test_normalize_skips_error_and_incomplete_records():
    assert linkedin_jobs._normalize({"job_posting_id": "1", "job_title": "X", "error": "dead_page"}, None) is None
    assert linkedin_jobs._normalize({"job_title": "No id"}, None) is None


@pytest.mark.parametrize(
    "title,summary,requested,expected",
    [
        # LinkedIn's own workplace-type filter is trusted when one was used.
        ("Backend Developer", "Nothing here says where the work happens.", "remote", "remote"),
        # A title that states its own work type wins over the filter.
        ("Backend Developer - Hybrid", "Two days a week in the office.", "remote", "hybrid"),
        # No filter: the same description scan every other source uses.
        ("Backend Developer", "This is a presencial role in Santiago.", None, "onsite"),
        ("Backend Developer", "Nothing here says where the work happens.", None, None),
    ],
)
def test_remote_tag(title, summary, requested, expected):
    job = linkedin_jobs._normalize({**RECORD, "job_title": title, "job_summary": summary}, requested)
    assert job["remote_type"] == expected


def test_empty_keyword_costs_nothing(monkeypatch):
    monkeypatch.setattr(linkedin_jobs.api_budget, "try_consume_budget", _never_spend)
    assert asyncio.run(linkedin_jobs.search_linkedin_jobs(q="   ")) == {"results": [], "has_more": False}


def test_missing_key_reads_as_not_configured(monkeypatch):
    # Discover keys its neutral "sin clave" badge on this exact wording.
    monkeypatch.setattr(linkedin_jobs.settings, "BRIGHTDATA_API_KEY", None)
    with pytest.raises(linkedin_jobs.LinkedInError, match="is not configured"):
        asyncio.run(linkedin_jobs.search_linkedin_jobs(q="C# developer"))


def test_cache_miss_starts_one_background_run_and_reports_pending(monkeypatch):
    started = []

    async def fake_refresh(key):
        started.append(key)

    async def allow(_provider):
        return True

    monkeypatch.setattr(linkedin_jobs, "_refresh", fake_refresh)
    monkeypatch.setattr(linkedin_jobs.api_budget, "try_consume_budget", allow)

    async def scenario():
        with pytest.raises(linkedin_jobs.LinkedInPending, match="segundo plano"):
            await linkedin_jobs.search_linkedin_jobs(q="C# developer", remote_type_filter="remote")
        # Still in flight: searching again must not start, or pay for, a second run.
        with pytest.raises(linkedin_jobs.LinkedInPending):
            await linkedin_jobs.search_linkedin_jobs(q="c#   Developer", remote_type_filter="remote")
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert started == [("c# developer", "Worldwide", "remote")]


def test_cache_hit_answers_without_paying_and_applies_the_remote_filter(monkeypatch):
    monkeypatch.setattr(linkedin_jobs.api_budget, "try_consume_budget", _never_spend)
    remote = linkedin_jobs._normalize(RECORD, "remote")
    hybrid = {**remote, "linkedin_job_id": "2", "remote_type": "hybrid"}
    linkedin_jobs._query_cache[("c# developer", "Worldwide", "remote")] = {
        "cached_at": linkedin_jobs.time.time(),
        "results": [remote, hybrid],
    }

    data = asyncio.run(linkedin_jobs.search_linkedin_jobs(q="C# developer", remote_type_filter="remote"))
    assert [job["linkedin_job_id"] for job in data["results"]] == ["4464695781"]


def test_recent_failure_is_reported_instead_of_paying_again(monkeypatch):
    monkeypatch.setattr(linkedin_jobs.api_budget, "try_consume_budget", _never_spend)
    key = ("c# developer", "Worldwide", "")
    linkedin_jobs._failures[key] = (linkedin_jobs.time.time(), "Bright Data rechazó la búsqueda (400)")
    with pytest.raises(linkedin_jobs.LinkedInError, match="400"):
        asyncio.run(linkedin_jobs.search_linkedin_jobs(q="C# developer"))


def test_refresh_fills_both_caches_and_drops_error_records(monkeypatch):
    async def fake_run(_key):
        return [RECORD, {"job_posting_id": "9", "job_title": "Gone", "error": "dead_page"}]

    monkeypatch.setattr(linkedin_jobs, "_run_discovery", fake_run)
    key = ("c# developer", "Worldwide", "remote")
    asyncio.run(linkedin_jobs._refresh(key))

    assert [job["linkedin_job_id"] for job in linkedin_jobs._query_cache[key]["results"]] == ["4464695781"]
    assert linkedin_jobs.get_cached_result("4464695781")["company"] == "BairesDev"
    assert key not in linkedin_jobs._in_flight


def test_refresh_records_a_failure_instead_of_raising(monkeypatch):
    async def fail(_key):
        raise linkedin_jobs.LinkedInError("Bright Data rechazó la búsqueda (400)")

    monkeypatch.setattr(linkedin_jobs, "_run_discovery", fail)
    key = ("c# developer", "Worldwide", "")
    asyncio.run(linkedin_jobs._refresh(key))  # must not raise: nothing awaits this task
    assert "400" in linkedin_jobs._failures[key][1]
