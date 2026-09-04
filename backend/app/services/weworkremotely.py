"""We Work Remotely — public RSS feed, no API key, no auth header.
Docs: https://weworkremotely.com/remote-job-rss-feed

The feed's own terms allow reuse, on condition of linking back to the
original listing (satisfied automatically here — `source_url` is always
the real weworkremotely.com job page, which is what the UI links out to).

Fair-use note: the feed's own `ttl` is 60 minutes, so this module caches
for the same window rather than re-fetching the whole ~50-listing feed on
every search.
"""

from __future__ import annotations

import time
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from xml.etree import ElementTree

import httpx

from app.services import experience_level
from app.services.job_importer import html_to_text, parse_job_text_heuristic

RSS_URL = "https://weworkremotely.com/remote-jobs.rss"
_CACHE_TTL_SECONDS = 60 * 60

_feed_cache: dict[str, Any] = {}
_search_cache: dict[str, dict[str, Any]] = {}

_EMPLOYMENT_TYPES = {
    "full-time": "full_time",
    "part-time": "part_time",
    "contract": "contract",
    "freelance": "contract",
    "internship": "internship",
}


class WeWorkRemotelyError(RuntimeError):
    pass


def _text_of(item: ElementTree.Element, tag: str) -> Optional[str]:
    el = item.find(tag)
    if el is None or not el.text:
        return None
    return el.text.strip() or None


def _normalize(item: ElementTree.Element) -> Optional[dict[str, Any]]:
    guid = _text_of(item, "guid")
    raw_title = _text_of(item, "title")
    if not guid or not raw_title:
        return None

    # Titles are conventionally "Company: Role" — falls back to the whole
    # thing as the role if there's no colon to split on.
    company, sep, role = raw_title.partition(":")
    if sep:
        company, role = company.strip(), role.strip()
    else:
        company, role = "Unknown company", raw_title.strip()

    description_text = html_to_text(_text_of(item, "description") or "")
    full_text = description_text if description_text.strip() else role
    parsed = parse_job_text_heuristic(full_text, title_hint=role, company_hint=company)

    posted_at = None
    pub_date = _text_of(item, "pubDate")
    if pub_date:
        try:
            posted_at = parsedate_to_datetime(pub_date)
        except (TypeError, ValueError):
            posted_at = None

    job_type = (_text_of(item, "type") or "").lower()
    employment_type = _EMPLOYMENT_TYPES.get(job_type, parsed["employment_type"])

    return {
        "wwr_job_id": guid.rstrip("/").rsplit("/", 1)[-1],
        "source": "weworkremotely",
        "source_url": guid,
        "title": role,
        "company": company,
        "location": _text_of(item, "region") or "Worldwide (remote)",
        "remote_type": "remote",
        "employment_type": employment_type,
        "seniority": parsed["seniority"],
        "description": description_text or role,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"],
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
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(RSS_URL)
    except httpx.HTTPError as exc:
        raise WeWorkRemotelyError("Could not reach We Work Remotely (network error).") from exc
    if resp.status_code != 200:
        raise WeWorkRemotelyError(f"We Work Remotely request failed with status {resp.status_code}.")
    try:
        root = ElementTree.fromstring(resp.content)
    except ElementTree.ParseError as exc:
        raise WeWorkRemotelyError("We Work Remotely returned a non-XML response.") from exc

    jobs = [j for j in (_normalize(item) for item in root.iter("item")) if j]
    _feed_cache["jobs"] = jobs
    _feed_cache["fetched_at"] = now
    return jobs


async def search_weworkremotely_jobs(
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
            haystack = f"{job['title']} {job['description']} {' '.join(s['name'] for s in job['skills_required'])}".lower()
            if q.lower() not in haystack:
                continue
        loc = (location or "").strip().lower()
        if loc and loc not in ("worldwide", "remote", "remoto"):
            if not job["location"] or loc not in job["location"].lower():
                continue
        if remote_type_filter and job["remote_type"] != remote_type_filter:
            continue
        if not experience_level.matches(job["seniority"], experience_level_filter):
            continue
        _search_cache[job["wwr_job_id"]] = {"cached_at": now, "job": job}
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
