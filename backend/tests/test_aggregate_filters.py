"""Discover's "Remoto" filter has to survive the providers' own answers.

Asked for remote, sources still return postings whose own title says
"Hybrid - San Francisco, New York City, Austin" — which is what the first
screen of a remote search actually looked like on the phone, followed by a
Berlin and a Köln role. The posting's own words win over the filter the
source was given.
"""

import pytest

from app.api.v1.routers import jobs


def _posting(job_id: str, title: str, location: str | None = None) -> dict:
    return {
        "himalayas_job_id": job_id,
        "source": "himalayas",
        "title": title,
        "company": "Acme",
        "location": location,
        "remote_type": None,
        "description": "Build things.",
    }


@pytest.mark.asyncio
async def test_postings_that_contradict_the_work_type_are_dropped(
    async_client, user_and_headers, monkeypatch
):
    _user, headers = user_and_headers

    async def fake_search(**_kwargs):
        return {
            "results": [
                _posting("1", "Backend Engineer", "Remote"),
                _posting("2", "Frontend Engineer (Hybrid - San Francisco, New York City)"),
                _posting("3", "Platform Engineer", "Köln, Germany (On-site)"),
            ],
            "has_more": False,
        }

    monkeypatch.setattr(jobs, "_SEARCH_PROVIDERS", {"himalayas"})
    monkeypatch.setattr(jobs.himalayas, "search_himalayas_jobs", fake_search)

    response = await async_client.get(
        "/jobs/search/aggregate",
        params={"q": "engineer", "remote_type": "remote"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    titles = [r["title"] for r in response.json()["results"]]
    assert titles == ["Backend Engineer"]


@pytest.mark.asyncio
async def test_a_posting_that_says_nothing_is_kept(async_client, user_and_headers, monkeypatch):
    """Most postings never state the work type. Dropping those would empty
    the search; the filter only removes the ones that actively disagree."""
    _user, headers = user_and_headers

    async def fake_search(**_kwargs):
        return {"results": [_posting("1", "Backend Engineer", "Worldwide")], "has_more": False}

    monkeypatch.setattr(jobs, "_SEARCH_PROVIDERS", {"himalayas"})
    monkeypatch.setattr(jobs.himalayas, "search_himalayas_jobs", fake_search)

    response = await async_client.get(
        "/jobs/search/aggregate",
        params={"q": "engineer", "remote_type": "remote"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert [r["title"] for r in response.json()["results"]] == ["Backend Engineer"]
