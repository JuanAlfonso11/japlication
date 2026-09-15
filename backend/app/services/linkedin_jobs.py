"""LinkedIn job search through LinkedIn's public, logged-out job pages.

LinkedIn offers no job search API a personal app can get (see
docs/PUBLIC_APIS_RESEARCH.md). The pages it serves to visitors who aren't
signed in need no account or key, though: a search returns a page of ten job
cards as HTML, and each posting has its own page with the full description.
No LinkedIn account is involved, so none can be restricted for it. Ported
from the linkedin-search skill in MadsLorentzen/ai-job-search (MIT).

It replaced Bright Data, which paid per record and took 45-90 seconds a run.
These pages answer in under a second, so a search waits for them like any
other source.

KEEPING VOLUME LOW
LinkedIn's terms forbid automated access. What it can do about a busy IP is
rate-limit it for a while (HTTP 429), which shows up as this source's error and
is never retried in a loop. To stay well clear of that:
- Results are cached per (keyword, location, work type) for an hour.
- A search reads one page: 10 postings from the past week.
- Posting pages are fetched a few at a time, not all at once.
- No keyword, no request.

THE REMOTE TAG
LinkedIn applies its own workplace-type filter (f_WT) at search time. That is
the structured value the employer set, so a posting from a filtered search
carries the requested type — the cards have no work-type field of their own to
read it back from. Two exceptions: a title that states its own work type wins
(a "Hybrid" posting that slipped into a remote search is tagged hybrid and
filtered out), and a search with no work-type filter falls back to the
description keyword scan every other source uses.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.services.external_jobs import http as external_http
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services import experience_level
from app.services.job_importer import _extract_remote_type, parse_job_text_heuristic

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
POSTING_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobPilot/1.0)", "Accept-Language": "en-US,en;q=0.9"}
_PAST_WEEK = "r604800"  # f_TPR means "posted within N seconds"
_RESULTS_TTL_SECONDS = 60 * 60
_POSTINGS_AT_ONCE = 3

_WORK_TYPES = {"onsite": "1", "remote": "2", "hybrid": "3"}
_EMPLOYMENT_TYPES = {
    "full-time": "full_time",
    "part-time": "part_time",
    "contract": "contract",
    "temporary": "contract",
    "internship": "internship",
}
_SENIORITY = {
    "internship": "internship",
    "entry level": "entry",
    "associate": "mid",
    "mid-senior level": "senior",
    "director": "lead",
    "executive": "lead",
}

Key = tuple[str, str, str]  # (keyword, location, work type)

# ponytail: in-process caches for a single uvicorn worker — lost on restart and
# not shared between workers. Move to Redis or a table if the backend ever runs
# more than one process.
_query_cache: dict[Key, dict[str, Any]] = {}
_job_cache: dict[str, dict[str, Any]] = {}


class LinkedInError(RuntimeError):
    pass


def _text(node: Any) -> Optional[str]:
    return (node.get_text(" ", strip=True) or None) if node is not None else None


def parse_cards(html: str) -> list[dict[str, Any]]:
    """The search page: one card per posting, marked with its job-posting URN."""
    cards = []
    for card in BeautifulSoup(html, "lxml").select('[data-entity-urn^="urn:li:jobPosting:"]'):
        title = _text(card.select_one(".base-search-card__title"))
        if not title:
            continue
        job_id = card["data-entity-urn"].rsplit(":", 1)[-1]
        link = card.select_one("a.base-card__full-link[href]")
        listed = card.select_one('time[class*="job-search-card__listdate"]')
        cards.append(
            {
                "id": job_id,
                "title": title,
                "company": _text(card.select_one(".base-search-card__subtitle")),
                "location": _text(card.select_one(".job-search-card__location")),
                # The query string is LinkedIn's own tracking.
                "url": link["href"].split("?", 1)[0] if link else f"https://www.linkedin.com/jobs/view/{job_id}",
                "date": listed.get("datetime") if listed else None,
                "date_text": _text(listed),
            }
        )
    return cards


def parse_posting(html: str) -> dict[str, Optional[str]]:
    """A posting page: the full description and the job-criteria list."""
    soup = BeautifulSoup(html, "lxml")
    criteria = {
        (_text(item.select_one(".description__job-criteria-subheader")) or "").lower(): _text(
            item.select_one(".description__job-criteria-text")
        )
        for item in soup.select(".description__job-criteria-item")
    }
    body = soup.select_one(".show-more-less-html__markup") or soup.select_one(".description__text")
    return {
        "description": body.get_text("\n", strip=True) if body else None,
        "seniority": criteria.get("seniority level"),
        "employment_type": criteria.get("employment type"),
    }


def _posted_at(value: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc) if value else None
    except ValueError:
        return None


def _normalize(card: dict[str, Any], posting: dict[str, Optional[str]], requested_work_type: Optional[str]) -> dict[str, Any]:
    title = card["title"]
    company = card["company"] or "Unknown company"
    description = posting.get("description") or "No description provided."
    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    return {
        "linkedin_job_id": card["id"],
        "source": "linkedin",
        "source_url": card["url"],
        "title": title,
        "company": company,
        "location": card["location"],
        # See THE REMOTE TAG in the module docstring.
        "remote_type": _extract_remote_type(title) or requested_work_type or _extract_remote_type(description),
        "employment_type": _EMPLOYMENT_TYPES.get(
            (posting.get("employment_type") or "").lower(), parsed["employment_type"]
        ),
        # Like the remote tag, a title that states its level wins: employers fill
        # LinkedIn's field loosely (live results had "Senior ..." roles marked Internship).
        "seniority": experience_level.infer(title)
        or _SENIORITY.get((posting.get("seniority") or "").lower())
        or experience_level.infer(description),
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"],
        # ponytail: salaries are rare on guest cards; parse job-search-card__salary-info when one shows up.
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "posted_at": _posted_at(card["date"]),
        "posted_at_text": card["date_text"],
        "via": "LinkedIn",
    }


async def _fetch(client: httpx.AsyncClient, url: str, params: Optional[dict[str, str]] = None) -> str:
    resp = await client.get(url, params=params)
    if resp.status_code == 429:
        raise LinkedInError("LinkedIn está limitando las búsquedas desde esta conexión: vuelve a intentar en un rato.")
    resp.raise_for_status()
    return resp.text


async def _search(key: Key) -> list[dict[str, Any]]:
    keyword, location, work_type = key
    params = {"keywords": keyword, "location": location, "f_TPR": _PAST_WEEK, "start": "0"}
    if work_type in _WORK_TYPES:
        params["f_WT"] = _WORK_TYPES[work_type]
    slots = asyncio.Semaphore(_POSTINGS_AT_ONCE)

    # Keeps its own client on purpose, unlike the other 14 connectors: this
    # one issues many concurrent posting fetches behind a semaphore and reuses
    # a single connection pool for them. Per-request clients (what
    # external_http.get does) would be a regression here. What it does take
    # from the shared module is the configurable timeout — the 15.0 literal
    # that used to be here is exactly the kind of value the review flagged as
    # needing 15 edits to change.
    if external_http.is_circuit_open("linkedin"):
        raise LinkedInError("LinkedIn no responde desde hace rato; se omite temporalmente.")

    async with httpx.AsyncClient(
        headers=_HEADERS,
        timeout=external_http.timeout_seconds(),
        follow_redirects=True,
    ) as client:

        async def posting(job_id: str) -> dict[str, Optional[str]]:
            async with slots:
                try:
                    return parse_posting(await _fetch(client, POSTING_URL.format(job_id)))
                except (httpx.HTTPError, LinkedInError):
                    return {}  # the card still shows, just without its description

        try:
            cards = parse_cards(await _fetch(client, SEARCH_URL, params))
        except httpx.HTTPError as exc:
            raise LinkedInError("No se pudo contactar a LinkedIn.") from exc
        postings = await asyncio.gather(*(posting(card["id"]) for card in cards))

    return [_normalize(card, info, work_type or None) for card, info in zip(cards, postings)]


async def search_linkedin_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
) -> dict[str, Any]:
    keyword = " ".join((q or "").split()).lower()
    if not keyword:
        return {"results": [], "has_more": False}

    key: Key = (keyword, (location or settings.LINKEDIN_LOCATION).strip(), remote_type_filter or "")
    now = time.time()
    cached = _query_cache.get(key)
    if cached is None or now - cached["cached_at"] > _RESULTS_TTL_SECONDS:
        jobs = await _search(key)
        cached = _query_cache[key] = {"cached_at": now, "results": jobs}
        for stale_id in [j for j, e in _job_cache.items() if now - e["cached_at"] > _RESULTS_TTL_SECONDS]:
            del _job_cache[stale_id]
        for job in jobs:
            _job_cache[job["linkedin_job_id"]] = {"cached_at": now, "job": job}

    results = [
        job
        for job in cached["results"]
        if not (remote_type_filter and job["remote_type"] and job["remote_type"] != remote_type_filter)
        and experience_level.matches(job["seniority"], experience_level_filter)
    ]
    return {"results": results, "has_more": False}


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _job_cache.get(job_id)
    if entry is None or time.time() - entry["cached_at"] > _RESULTS_TTL_SECONDS:
        _job_cache.pop(job_id, None)
        return None
    return entry["job"]
