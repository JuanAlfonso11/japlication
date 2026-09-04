"""Hacker News "Who is hiring?" — the monthly Ask HN thread posted by the
@whoishiring bot on the 1st of every month, read through the official,
free, no-key Algolia HN Search API (hn.algolia.com), not the raw Firebase
API — Algolia's `/items/{id}` returns the whole comment tree (including
job postings) in one request instead of one call per comment.
Docs: https://hn.algolia.com/api

Job postings are plain-text top-level comments, not structured data — by
loose community convention "Company | Role | Location | Type | Salary |
URL" on the first line, then free-form text. That convention isn't
enforced, so parsing here is best-effort: split the first line on "|" for
company/role/location, then run the same heuristic requirements/skills
extractor `job_importer.py` uses for scraped/pasted job text over
whatever's left.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

import httpx

from app.services import experience_level
from app.services.job_importer import html_to_text, parse_job_text_heuristic

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
ITEM_URL = "https://hn.algolia.com/api/v1/items/{item_id}"

# The thread only gets new top-level comments for a few days after it's
# posted, then stays static for the rest of the month — no need to poll
# more often than a few times a day.
_CACHE_TTL_SECONDS = 6 * 60 * 60

_thread_cache: dict[str, Any] = {}
_search_cache: dict[str, dict[str, Any]] = {}


class HackerNewsError(RuntimeError):
    pass


def _parse_posting(comment: dict[str, Any]) -> Optional[dict[str, Any]]:
    raw_html = comment.get("text")
    comment_id = comment.get("id")
    if not raw_html or comment_id is None:
        return None
    text = html_to_text(raw_html)
    if not text.strip():
        return None

    first_line = text.split("\n", 1)[0]
    parts = [p.strip() for p in first_line.split("|") if p.strip()]
    company = parts[0] if parts else "Unknown company"
    role = parts[1] if len(parts) > 1 else first_line[:140]
    location = parts[2] if len(parts) > 2 else None

    parsed = parse_job_text_heuristic(text, title_hint=role, company_hint=company)

    posted_at = None
    created_at = comment.get("created_at")
    if created_at:
        try:
            posted_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    return {
        "hn_job_id": str(comment_id),
        "source": "hackernews",
        "source_url": f"https://news.ycombinator.com/item?id={comment_id}",
        "title": parsed["title"],
        "company": parsed["company"],
        "location": location,
        "remote_type": parsed["remote_type"],
        "employment_type": parsed["employment_type"],
        "seniority": parsed["seniority"],
        "description": parsed["description"],
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"],
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "posted_at": posted_at,
    }


async def _current_thread_jobs() -> list[dict[str, Any]]:
    now = time.time()
    cached_jobs = _thread_cache.get("jobs")
    if cached_jobs is not None and now - _thread_cache.get("fetched_at", 0) < _CACHE_TTL_SECONDS:
        return cached_jobs

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                SEARCH_URL, params={"tags": "story,author_whoishiring", "hitsPerPage": 5}
            )
    except httpx.HTTPError as exc:
        raise HackerNewsError("Could not reach Hacker News / Algolia (network error).") from exc
    if resp.status_code != 200:
        raise HackerNewsError(f"HN search request failed with status {resp.status_code}.")

    thread_id = None
    for hit in resp.json().get("hits", []):
        if (hit.get("title") or "").startswith("Ask HN: Who is hiring?"):
            thread_id = hit.get("objectID")
            break
    if thread_id is None:
        raise HackerNewsError("Could not find this month's 'Who is hiring?' thread.")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(ITEM_URL.format(item_id=thread_id))
    except httpx.HTTPError as exc:
        raise HackerNewsError("Could not reach Hacker News / Algolia (network error).") from exc
    if resp.status_code != 200:
        raise HackerNewsError(f"HN thread request failed with status {resp.status_code}.")

    thread = resp.json()
    jobs = []
    for comment in thread.get("children") or []:
        if comment.get("dead") or comment.get("deleted"):
            continue
        parsed = _parse_posting(comment)
        if parsed:
            jobs.append(parsed)

    _thread_cache["jobs"] = jobs
    _thread_cache["fetched_at"] = now
    return jobs


async def search_hackernews_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
) -> dict[str, Any]:
    jobs = await _current_thread_jobs()

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
        if remote_type_filter and job["remote_type"] and job["remote_type"] != remote_type_filter:
            continue
        if not experience_level.matches(job["seniority"], experience_level_filter):
            continue
        _search_cache[job["hn_job_id"]] = {"cached_at": now, "job": job}
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
