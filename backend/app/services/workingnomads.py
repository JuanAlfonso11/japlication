"""Working Nomads — free, no API key, no registration.

`https://www.workingnomads.com/api/exposed_jobs/` returns the full set of
currently-open remote listings as one JSON array. Verified live before
integrating: it answers 200 with the project's own User-Agent (no
Cloudflare gate, unlike several other candidates that only respond to a
browser string), and every record carries the fields this app needs —
company, title, description, location, tags and a URL.

There is no query parameter: the endpoint always returns everything, so
filtering happens here over the cached feed, the same shape as the We Work
Remotely and Hacker News providers.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

import httpx

from app.services.external_jobs import http as external_http

from app.services import experience_level
from app.services.job_importer import html_to_text, parse_job_text_heuristic

ENDPOINT = "https://www.workingnomads.com/api/exposed_jobs/"

# The feed is the whole board, so one fetch serves every search in the
# window. Fifteen minutes matches the other feed-shaped providers and keeps
# a burst of searches from re-downloading a couple hundred KB each time.
_CACHE_TTL_SECONDS = 15 * 60

_feed_cache: dict[str, Any] = {}
_search_cache: dict[str, dict[str, Any]] = {}


class WorkingNomadsError(RuntimeError):
    pass


def _normalize(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    url = raw.get("url")
    title = (raw.get("title") or "").strip()
    if not url or not title:
        # Without a URL there is nothing to apply to, and without a title
        # the row is unusable in the swipe deck.
        return None

    company = (raw.get("company_name") or "").strip() or "Unknown company"
    description = html_to_text(raw.get("description") or "").strip() or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    # `tags` is a comma-separated string ("sap,architecture,cloud"), not a
    # list — merged with whatever the heuristic parser found in the body so
    # the match engine sees both.
    tag_names = [t.strip() for t in str(raw.get("tags") or "").split(",") if t.strip()]
    skills = list(parsed["skills_required"])
    seen = {s["name"].lower() for s in skills}
    for name in tag_names:
        if name.lower() not in seen:
            skills.append({"name": name, "importance": "required"})
            seen.add(name.lower())

    posted_at = None
    pub_date = raw.get("pub_date")
    if pub_date:
        try:
            posted_at = datetime.fromisoformat(str(pub_date).replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    # Working Nomads is a remote-only board; its `location` field describes
    # the constraint ("Time zone: CET (+/- 3 hours)", "USA only"), not an
    # office, so it goes through as the location text with remote_type
    # pinned rather than being parsed as a city.
    location = (raw.get("location") or "").strip() or "Remote"

    return {
        "workingnomads_job_id": url,
        "source": "workingnomads",
        "source_url": url,
        "title": title,
        "company": company,
        "location": location,
        "remote_type": "remote",
        "employment_type": parsed["employment_type"],
        "seniority": experience_level.infer(title, description),
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": skills,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "posted_at": posted_at,
    }


async def _all_jobs() -> list[dict[str, Any]]:
    now = time.time()
    cached_jobs = _feed_cache.get("jobs")
    if cached_jobs is not None and now - _feed_cache.get("fetched_at", 0) < _CACHE_TTL_SECONDS:
        return cached_jobs

    try:
        resp = await external_http.get("workingnomads", ENDPOINT, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise WorkingNomadsError("Could not reach Working Nomads (network error).") from exc

    if resp.status_code != 200:
        raise WorkingNomadsError(
            f"Working Nomads request failed with status {resp.status_code}."
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        raise WorkingNomadsError("Working Nomads returned a non-JSON response.") from exc

    if not isinstance(payload, list):
        raise WorkingNomadsError("Working Nomads returned an unexpected payload shape.")

    jobs = [j for j in (_normalize(raw) for raw in payload if isinstance(raw, dict)) if j]
    _feed_cache["jobs"] = jobs
    _feed_cache["fetched_at"] = now
    return jobs


async def search_workingnomads_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
) -> dict[str, Any]:
    jobs = await _all_jobs()

    now = time.time()
    results = []
    for job in jobs:
        if q:
            haystack = (
                f"{job['title']} {job['company']} {job['description']} "
                f"{' '.join(s['name'] for s in job['skills_required'])}"
            ).lower()
            if q.lower() not in haystack:
                continue
        loc = (location or "").strip().lower()
        if loc and loc not in ("worldwide", "remote", "remoto"):
            if not job["location"] or loc not in job["location"].lower():
                continue
        # Everything here is remote by definition, so a hybrid/onsite filter
        # correctly excludes the whole provider rather than returning
        # remote jobs that don't match what was asked for.
        if remote_type_filter and remote_type_filter != "remote":
            continue
        if not experience_level.matches(job["seniority"], experience_level_filter):
            continue
        _search_cache[job["workingnomads_job_id"]] = {"cached_at": now, "job": job}
        results.append(job)
    _cleanup_cache(now)

    return {"results": results, "has_more": False}


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
