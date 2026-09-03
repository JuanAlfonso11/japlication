"""Arbeitnow Job Board API — free, no API key.
Docs: https://www.arbeitnow.com/api/job-board-api

No native keyword-search or experience-level parameter, so `q` and
`experience_level` are applied client-side after fetching a page.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.services import experience_level
from app.services.job_importer import html_to_text, parse_job_text_heuristic

ENDPOINT = "https://www.arbeitnow.com/api/job-board-api"
_CACHE_TTL_SECONDS = 15 * 60
_search_cache: dict[str, dict[str, Any]] = {}


class ArbeitnowError(RuntimeError):
    pass


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    title = raw.get("title") or "Untitled position"
    company = raw.get("company_name") or "Unknown company"
    description = html_to_text(raw.get("description") or "").strip() or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    job_types = [str(t) for t in (raw.get("job_types") or [])]
    is_remote = bool(raw.get("remote"))
    location = raw.get("location") or ("Remote" if is_remote else None) or parsed["location"]

    level = None
    if any("trainee" in t.lower() or "intern" in t.lower() for t in job_types):
        level = "internship"
    if level is None:
        level = experience_level.infer(title, description)

    posted_at = None
    created_at = raw.get("created_at")
    if isinstance(created_at, (int, float)):
        try:
            posted_at = datetime.fromtimestamp(created_at, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            posted_at = None

    known = {s["name"].lower() for s in parsed["skills_required"]}
    extra_skills = [
        {"name": t, "importance": "nice_to_have"} for t in raw.get("tags") or [] if t and t.lower() not in known
    ]

    return {
        "arbeitnow_job_id": raw.get("slug"),
        "source": "arbeitnow",
        "source_url": raw.get("url"),
        "title": title,
        "company": company,
        "location": location,
        "remote_type": "remote" if is_remote else parsed["remote_type"],
        "employment_type": parsed["employment_type"],
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


async def search_arbeitnow_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    page: int = 1,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(ENDPOINT, params={"page": page})
    except httpx.HTTPError as exc:
        raise ArbeitnowError("Could not reach Arbeitnow (network error).") from exc

    if resp.status_code != 200:
        raise ArbeitnowError(f"Arbeitnow request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise ArbeitnowError("Arbeitnow returned a non-JSON response.") from exc

    now = time.time()
    results = []
    for raw in data.get("data", []) or []:
        normalized = _normalize(raw)

        if q:
            haystack = f"{normalized['title']} {normalized['description']} {' '.join(s['name'] for s in normalized['skills_required'])}".lower()
            if q.lower() not in haystack:
                continue
        loc = (location or "").strip().lower()
        if loc in ("remote", "remoto"):
            if normalized["remote_type"] != "remote":
                continue
        elif loc:
            if not normalized["location"] or loc not in normalized["location"].lower():
                continue
        if not experience_level.matches(normalized["seniority"], experience_level_filter):
            continue

        if normalized["arbeitnow_job_id"]:
            _search_cache[normalized["arbeitnow_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    has_more = bool((data.get("links") or {}).get("next"))
    return {"results": results, "has_more": has_more}


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
