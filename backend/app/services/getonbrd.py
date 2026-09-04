"""Get on Board — LatAm-focused job board (Chile-based, strong coverage
across the region). Public search API, no key/registration required.
Docs: https://api-doc.getonbrd.com/ (SPA, best read via the official Ruby
client's source, github.com/getonbrd/getonbrd-ruby, which this module's
request shape mirrors) — confirmed live: GET /api/v0/jobs (plain listing)
returns 401 without an API key, but GET /api/v0/search/jobs?query=...
(the "public facet") works with no auth at all.

The public search endpoint requires `query` to be at least 3 characters
— unlike the fully-open providers, there's no "browse everything"
fallback — so a missing/too-short `q` falls back to the broad term
"remote" rather than erroring, mirroring Himalayas' `worldwide` trick
for the no-query case.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.services import experience_level
from app.services.job_importer import html_to_text, parse_job_text_heuristic

BASE_URL = "https://www.getonbrd.com/api/v0"
_CACHE_TTL_SECONDS = 15 * 60
_search_cache: dict[str, dict[str, Any]] = {}

_EMPLOYMENT_TYPE_MAP = {"full_time": "full_time", "part_time": "part_time", "freelance": "contract", "internship": "internship"}


class GetOnBrdError(RuntimeError):
    pass


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    attrs = raw.get("attributes") or {}
    title = attrs.get("title") or "Untitled position"

    company_data = ((attrs.get("company") or {}).get("data")) or {}
    company = (company_data.get("attributes") or {}).get("name") or "Unknown company"

    html_parts = [attrs.get(k) or "" for k in ("description", "functions", "desirable", "benefits")]
    description = html_to_text("\n".join(html_parts)).strip() or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    modality = ((attrs.get("modality") or {}).get("data") or {}).get("attributes") or {}
    employment_type = _EMPLOYMENT_TYPE_MAP.get(modality.get("locale_key") or "", parsed["employment_type"])

    seniority_attrs = ((attrs.get("seniority") or {}).get("data") or {}).get("attributes") or {}
    level = experience_level.normalize_native(seniority_attrs.get("name")) or parsed.get("seniority")

    is_remote = bool(attrs.get("remote"))
    remote_type = "remote" if is_remote else ("hybrid" if attrs.get("remote_modality") == "hybrid" else "onsite")

    countries = attrs.get("countries") or []
    if countries and countries != ["Remote"]:
        location = ", ".join(countries)
    elif is_remote:
        location = "Remote"
    else:
        location = None

    posted_at = None
    published_at = attrs.get("published_at")
    if published_at:
        try:
            posted_at = datetime.fromtimestamp(int(published_at), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            posted_at = None

    min_salary = attrs.get("min_salary")
    max_salary = attrs.get("max_salary")

    links = raw.get("links") or {}

    return {
        "getonbrd_job_id": str(raw.get("id")) if raw.get("id") else None,
        "source": "getonbrd",
        "source_url": links.get("public_url"),
        "title": title,
        "company": company,
        "location": location,
        "remote_type": remote_type,
        "employment_type": employment_type,
        "seniority": level,
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"],
        "salary_min": min_salary,
        "salary_max": max_salary,
        "salary_currency": "USD" if is_remote and (min_salary or max_salary) else None,
        "posted_at": posted_at,
        "category": attrs.get("category_name"),
    }


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def search_getonbrd_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> dict[str, Any]:
    search_term = q.strip() if q and len(q.strip()) >= 3 else "remote"

    params: dict[str, Any] = {
        "query": search_term,
        "page": page,
        "per_page": per_page,
        "expand[]": ["company", "modality", "seniority"],
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{BASE_URL}/search/jobs", params=params)
    except httpx.HTTPError as exc:
        raise GetOnBrdError("Could not reach Get on Board (network error).") from exc

    if resp.status_code != 200:
        raise GetOnBrdError(f"Get on Board request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise GetOnBrdError("Get on Board returned a non-JSON response.") from exc

    now = time.time()
    results = []
    for raw in data.get("data", []) or []:
        normalized = _normalize(raw)

        loc = (location or "").strip().lower()
        if loc and loc not in ("worldwide", "remote", "remoto"):
            if loc not in (normalized["location"] or "").lower():
                continue
        if remote_type_filter and normalized["remote_type"] and normalized["remote_type"] != remote_type_filter:
            continue
        if not experience_level.matches(normalized["seniority"], experience_level_filter):
            continue

        if normalized["getonbrd_job_id"]:
            _search_cache[normalized["getonbrd_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    meta = data.get("meta") or {}
    has_more = bool(meta.get("page") and meta.get("total_pages") and meta["page"] < meta["total_pages"])

    return {"results": results, "has_more": has_more}


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
