"""RemoteJobs.org API — free, no account or API key required.
Docs: https://remotejobs.org/api-access

No native experience-level field or parameter, so the level filter is
applied client-side via the shared keyword heuristic.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

import httpx

from app.services import experience_level
from app.services.job_importer import html_to_text, parse_job_text_heuristic

ENDPOINT = "https://remotejobs.org/api/v1/jobs"
_CACHE_TTL_SECONDS = 15 * 60
_search_cache: dict[str, dict[str, Any]] = {}


class RemoteJobsOrgError(RuntimeError):
    pass


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    title = raw.get("title") or "Untitled position"
    company_obj = raw.get("company") or {}
    company = company_obj.get("name") or "Unknown company"
    description = html_to_text(raw.get("description") or "").strip() or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    job_type = str(raw.get("type") or "")
    employment_type = {
        "full-time": "full_time",
        "part-time": "part_time",
        "contract": "contract",
        "freelance": "contract",
    }.get(job_type, parsed["employment_type"])

    level = experience_level.infer(title, description)

    category_obj = raw.get("category") or {}
    known = {s["name"].lower() for s in parsed["skills_required"]}
    extra_skills = []
    if category_obj.get("name") and category_obj["name"].lower() not in known:
        extra_skills.append({"name": category_obj["name"], "importance": "nice_to_have"})

    posted_at = None
    posted = raw.get("posted_at")
    if posted:
        try:
            posted_at = datetime.fromisoformat(str(posted).replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    return {
        "remotejobs_org_job_id": str(raw.get("id")) if raw.get("id") is not None else None,
        "source": "remotejobs_org",
        "source_url": raw.get("apply_url") or raw.get("url"),
        "title": title,
        "company": company,
        "location": raw.get("location") or "Worldwide (remote)",
        "remote_type": "remote",
        "employment_type": employment_type,
        "seniority": level,
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"] + extra_skills,
        "salary_min": raw.get("salary_min"),
        "salary_max": raw.get("salary_max"),
        "salary_currency": None,
        "posted_at": posted_at,
    }


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def search_remotejobs_org_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
    category: Optional[str] = None,
    job_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": min(limit, 50), "offset": offset}
    if q:
        params["q"] = q
    if category:
        params["category"] = category
    if job_type:
        params["type"] = job_type

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(ENDPOINT, params=params)
    except httpx.HTTPError as exc:
        raise RemoteJobsOrgError("Could not reach RemoteJobs.org (network error).") from exc

    if resp.status_code != 200:
        raise RemoteJobsOrgError(f"RemoteJobs.org request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise RemoteJobsOrgError("RemoteJobs.org returned a non-JSON response.") from exc

    jobs = data.get("data") or []
    now = time.time()
    results = []
    for raw in jobs or []:
        normalized = _normalize(raw)

        if q:
            # RemoteJobs.org's own `q` param (sent above) doesn't actually
            # filter by relevance -- searching "Software Developer" comes
            # back with things like "Product Marketing Manager" and
            # "Medical Underwriting Nurse" mixed in untouched. Re-filter
            # client-side, same substring approach already used for
            # Arbeitnow/The Muse, whose APIs have the same gap.
            haystack = f"{normalized['title']} {normalized['description']} {' '.join(s['name'] for s in normalized['skills_required'])}".lower()
            if q.lower() not in haystack:
                continue

        loc = (location or "").strip().lower()
        if loc and loc not in ("worldwide", "remote", "remoto"):
            if loc not in (normalized["location"] or "").lower():
                continue
        if remote_type_filter and normalized["remote_type"] and normalized["remote_type"] != remote_type_filter:
            continue
        if not experience_level.matches(normalized["seniority"], experience_level_filter):
            continue

        if normalized["remotejobs_org_job_id"]:
            _search_cache[normalized["remotejobs_org_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    pagination = data.get("pagination") or {}
    has_more = bool(pagination.get("has_more"))
    return {"results": results, "has_more": has_more}


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
