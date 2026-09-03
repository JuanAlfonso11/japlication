"""Jobicy Remote Jobs API — free, no API key, no auth header.
Docs: https://jobicy.com/api/v2/remote-jobs

Has a native `jobLevel` field on every result (values seen in the wild:
"Senior", "Midweight", "Entry Level", "Junior", ...) but no query parameter
to filter by it server-side, so the level filter is applied client-side
after normalizing `jobLevel` through the shared taxonomy.

Fair-use note from Jobicy: automated checks should run at most about once
an hour — this module makes one request per search and relies on the
shared short-lived cache, never polls in a loop.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.services import experience_level
from app.services.job_importer import html_to_text, parse_job_text_heuristic

ENDPOINT = "https://jobicy.com/api/v2/remote-jobs"
_CACHE_TTL_SECONDS = 15 * 60
_search_cache: dict[str, dict[str, Any]] = {}


class JobicyError(RuntimeError):
    pass


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    title = raw.get("jobTitle") or "Untitled position"
    company = raw.get("companyName") or "Unknown company"
    description = html_to_text(raw.get("jobDescription") or "").strip() or (raw.get("jobExcerpt") or "").strip() or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    job_type_list = raw.get("jobType") or []
    employment_type = parsed["employment_type"]
    if job_type_list:
        first = str(job_type_list[0]).lower().replace("-", " ")
        employment_type = {
            "full time": "full_time",
            "part time": "part_time",
            "contract": "contract",
            "freelance": "contract",
            "internship": "internship",
        }.get(first, employment_type)

    level = experience_level.normalize_native(raw.get("jobLevel")) or experience_level.infer(title, description)

    industries = raw.get("jobIndustry") or []
    known = {s["name"].lower() for s in parsed["skills_required"]}
    extra_skills = [
        {"name": i, "importance": "nice_to_have"} for i in industries if i and i.lower() not in known
    ]

    posted_at = None
    pub_date = raw.get("pubDate")
    if pub_date:
        try:
            posted_at = datetime.fromisoformat(str(pub_date).replace("Z", "+00:00").replace(" ", "T"))
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
        except ValueError:
            posted_at = None

    return {
        "jobicy_job_id": str(raw.get("id")) if raw.get("id") is not None else None,
        "source": "jobicy",
        "source_url": raw.get("url"),
        "title": title,
        "company": company,
        "location": raw.get("jobGeo") or "Worldwide (remote)",
        "remote_type": "remote",
        "employment_type": employment_type,
        "seniority": level,
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"] + extra_skills,
        "salary_min": raw.get("salaryMin"),
        "salary_max": raw.get("salaryMax"),
        "salary_currency": raw.get("salaryCurrency"),
        "posted_at": posted_at,
    }


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def search_jobicy_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    industry: Optional[str] = None,
    count: int = 50,
) -> dict[str, Any]:
    params: dict[str, Any] = {"count": count}
    if q:
        params["tag"] = q
    if industry:
        params["industry"] = industry
    geo = (location or "").strip().lower()
    if geo and geo not in ("remote", "remoto", "worldwide"):
        params["geo"] = geo

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(ENDPOINT, params=params)
    except httpx.HTTPError as exc:
        raise JobicyError("Could not reach Jobicy (network error).") from exc

    if resp.status_code != 200:
        raise JobicyError(f"Jobicy request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise JobicyError("Jobicy returned a non-JSON response.") from exc

    now = time.time()
    results = []
    for raw in data.get("jobs", []) or []:
        normalized = _normalize(raw)
        if not experience_level.matches(normalized["seniority"], experience_level_filter):
            continue
        if normalized["jobicy_job_id"]:
            _search_cache[normalized["jobicy_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    return {"results": results, "has_more": False}


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
