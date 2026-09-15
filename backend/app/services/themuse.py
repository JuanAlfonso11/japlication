"""The Muse Jobs API — `api_key` is optional (500 req/hour without one,
3,600/hour with a free registered key), so it qualifies as not requiring
authentication. Docs: https://www.themuse.com/developers/api/v2

Has native `location` and `level` query parameters — both are passed
through directly rather than filtered client-side. There's no native
keyword-search parameter, so `q` is applied client-side.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

import httpx

from app.services.external_jobs import http as external_http

from app.services import experience_level
from app.services.job_importer import html_to_text, parse_job_text_heuristic

ENDPOINT = "https://www.themuse.com/api/public/jobs"
_CACHE_TTL_SECONDS = 15 * 60
_search_cache: dict[str, dict[str, Any]] = {}

_EMPLOYMENT_MAP = {
    "full time": "full_time",
    "part time": "part_time",
    "contract": "contract",
    "internship": "internship",
    "labor hire": "contract",
}


class TheMuseError(RuntimeError):
    pass


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    title = raw.get("name") or "Untitled position"
    company = (raw.get("company") or {}).get("name") or "Unknown company"
    description = html_to_text(raw.get("contents") or "").strip() or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    locations = raw.get("locations") or []
    location_names = [l.get("name") for l in locations if isinstance(l, dict) and l.get("name")]
    location = ", ".join(location_names) if location_names else parsed["location"]
    is_remote = any("remote" in (n or "").lower() or "flexible" in (n or "").lower() for n in location_names)

    levels = raw.get("levels") or []
    level_name = levels[0].get("name") if levels and isinstance(levels[0], dict) else None
    level = experience_level.normalize_native(level_name) or experience_level.infer(title, description)

    employment_type = _EMPLOYMENT_MAP.get(str(raw.get("type") or "").lower(), parsed["employment_type"])

    categories = raw.get("categories") or []
    known = {s["name"].lower() for s in parsed["skills_required"]}
    extra_skills = [
        {"name": c.get("name"), "importance": "nice_to_have"}
        for c in categories
        if isinstance(c, dict) and c.get("name") and c["name"].lower() not in known
    ]

    posted_at = None
    pub_date = raw.get("publication_date")
    if pub_date:
        try:
            posted_at = datetime.fromisoformat(str(pub_date).replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    refs = raw.get("refs") or {}

    return {
        "themuse_job_id": str(raw.get("id")) if raw.get("id") is not None else None,
        "source": "themuse",
        "source_url": refs.get("landing_page"),
        "title": title,
        "company": company,
        "location": location,
        "remote_type": "remote" if is_remote else parsed["remote_type"],
        "employment_type": employment_type,
        "seniority": level,
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"] + extra_skills,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "posted_at": posted_at,
    }


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def search_themuse_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 0,
) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page}
    if location:
        params["location"] = location
    if experience_level_filter:
        muse_level = experience_level.to_muse(experience_level_filter)
        if muse_level:
            params["level"] = muse_level
    if category:
        params["category"] = category

    try:
        resp = await external_http.get("themuse", ENDPOINT, params=params)
    except httpx.HTTPError as exc:
        raise TheMuseError("Could not reach The Muse (network error).") from exc

    if resp.status_code != 200:
        raise TheMuseError(f"The Muse request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise TheMuseError("The Muse returned a non-JSON response.") from exc

    now = time.time()
    results = []
    for raw in data.get("results", []) or []:
        normalized = _normalize(raw)

        if q:
            haystack = f"{normalized['title']} {normalized['description']}".lower()
            if q.lower() not in haystack:
                continue
        if remote_type_filter and normalized["remote_type"] and normalized["remote_type"] != remote_type_filter:
            continue

        if normalized["themuse_job_id"]:
            _search_cache[normalized["themuse_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    has_more = (data.get("page") or 0) + 1 < (data.get("page_count") or 0)
    return {"results": results, "has_more": has_more}


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
