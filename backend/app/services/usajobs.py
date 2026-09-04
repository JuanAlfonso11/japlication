"""USAJobs — official US federal government jobs API. Free, instant
self-serve signup at https://developer.usajobs.gov/: a registered email
(sent as the User-Agent header) plus an Authorization-Key, both required
on every request. Docs:
https://developer.usajobs.gov/api-reference/get-api-search

USAJobs lists ONLY US federal government positions — not remote/tech
jobs generally — so it's a narrow, authoritative complement to the other
providers rather than a broad aggregator. Almost none of its postings
are remote, so with Discover's default remote_type=remote filter it will
typically show zero results unless the user explicitly widens the filter
or searches without a location constraint.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.services import experience_level
from app.services.job_importer import html_to_text, parse_job_text_heuristic

ENDPOINT = "https://data.usajobs.gov/api/search"
_CACHE_TTL_SECONDS = 30 * 60
_search_cache: dict[str, dict[str, Any]] = {}

_SCHEDULE_MAP = {"full-time": "full_time", "part-time": "part_time"}


class USAJobsError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.USAJOBS_API_KEY and settings.USAJOBS_USER_AGENT)


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    descriptor = raw.get("MatchedObjectDescriptor") or {}
    title = descriptor.get("PositionTitle") or "Untitled position"
    company = descriptor.get("OrganizationName") or "U.S. federal government"

    details = ((descriptor.get("UserArea") or {}).get("Details")) or {}
    summary = html_to_text(details.get("JobSummary") or "").strip()
    qualifications = html_to_text(details.get("QualificationSummary") or "").strip()
    full_text = "\n\n".join(t for t in [summary, qualifications] if t) or "No description provided."

    parsed = parse_job_text_heuristic(full_text, title_hint=title, company_hint=company)

    schedules = descriptor.get("PositionSchedule") or []
    schedule_name = ((schedules[0] or {}).get("Name") if schedules else "") or ""
    employment_type = _SCHEDULE_MAP.get(schedule_name.strip().lower(), parsed["employment_type"])

    level = experience_level.infer(title, full_text) or parsed.get("seniority")

    salary_min = salary_max = salary_currency = None
    remuneration = descriptor.get("PositionRemuneration") or []
    if remuneration:
        entry = remuneration[0] or {}
        try:
            salary_min = float(entry["MinimumRange"]) if entry.get("MinimumRange") not in (None, "") else None
            salary_max = float(entry["MaximumRange"]) if entry.get("MaximumRange") not in (None, "") else None
        except (TypeError, ValueError):
            salary_min = salary_max = None
        if salary_min is not None or salary_max is not None:
            salary_currency = "USD"

    posted_at = None
    pub_date = descriptor.get("PublicationStartDate")
    if pub_date:
        try:
            posted_at = datetime.fromisoformat(str(pub_date).replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    location_name = descriptor.get("PositionLocationDisplay")

    job_id = descriptor.get("PositionID") or raw.get("MatchedObjectId")

    return {
        "usajobs_job_id": str(job_id) if job_id else None,
        "source": "usajobs",
        "source_url": descriptor.get("PositionURI"),
        "title": title,
        "company": company,
        "location": location_name,
        "remote_type": "remote" if "remote" in (location_name or "").lower() else parsed.get("remote_type"),
        "employment_type": employment_type,
        "seniority": level,
        "description": full_text,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"],
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": salary_currency,
        "posted_at": posted_at,
    }


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def search_usajobs_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
    page: int = 1,
    results_per_page: int = 25,
) -> dict[str, Any]:
    if not is_configured():
        raise USAJobsError("USAJobs is not configured (missing USAJOBS_API_KEY/USAJOBS_USER_AGENT).")

    params: dict[str, Any] = {"ResultsPerPage": results_per_page, "Page": page}
    if q:
        params["Keyword"] = q
    if location:
        params["LocationName"] = location

    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": settings.USAJOBS_USER_AGENT,
        "Authorization-Key": settings.USAJOBS_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(ENDPOINT, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise USAJobsError("Could not reach USAJobs (network error).") from exc

    if resp.status_code != 200:
        raise USAJobsError(f"USAJobs request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise USAJobsError("USAJobs returned a non-JSON response.") from exc

    now = time.time()
    results = []
    search_result = data.get("SearchResult") or {}
    items = search_result.get("SearchResultItems") or []
    for raw in items:
        normalized = _normalize(raw)
        if remote_type_filter and normalized["remote_type"] and normalized["remote_type"] != remote_type_filter:
            continue
        if not experience_level.matches(normalized["seniority"], experience_level_filter):
            continue
        if normalized["usajobs_job_id"]:
            _search_cache[normalized["usajobs_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    total_count = search_result.get("SearchResultCountAll") or 0
    has_more = page * results_per_page < total_count

    return {"results": results, "has_more": has_more}


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
