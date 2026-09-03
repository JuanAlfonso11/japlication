"""Free, no-API-key remote job search via the Himalayas Remote Jobs API
(https://himalayas.app/docs/remote-jobs-api — browse: GET /jobs/api, search:
GET /jobs/api/search).

Unlike Google Jobs (SerpApi, metered, requires SERPAPI_API_KEY) or Upwork
(OAuth2, requires the user to connect their account), this source needs no
configuration and works for every user out of the box — it's the default
search provider. Results are normalized into the same Job-like shape used by
the other providers and cached briefly so `POST /jobs/search/import` doesn't
need a second request.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.services.job_importer import html_to_text, parse_job_text_heuristic

HIMALAYAS_SEARCH_ENDPOINT = "https://himalayas.app/jobs/api/search"
_CACHE_TTL_SECONDS = 15 * 60

# guid -> {"cached_at": float, "job": {...normalized...}}
_search_cache: dict[str, dict[str, Any]] = {}


class HimalayasError(RuntimeError):
    """Raised for any condition that should surface as a clean HTTP error."""


_SENIORITY_MAP = {
    "Entry-level": "entry level",
    "Mid-level": "mid level",
    "Senior": "senior",
    "Manager": "lead",
    "Director": "director",
    "Executive": "director",
}

_EMPLOYMENT_MAP = {
    "Full Time": "full_time",
    "Part Time": "part_time",
    "Contractor": "contract",
    "Temporary": "contract",
    "Intern": "internship",
    "Volunteer": "contract",
}


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    title = raw.get("title") or "Untitled position"
    company = raw.get("companyName") or "Unknown company"

    description_html = raw.get("description") or ""
    description = html_to_text(description_html) if description_html else ""
    description = description.strip() or (raw.get("excerpt") or "").strip() or "No description provided."

    # Reuse the same heuristic extractor the URL importer uses for
    # requirements/responsibilities and a free-text skills scan.
    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    location_restrictions = raw.get("locationRestrictions") or []
    location = ", ".join(location_restrictions) if location_restrictions else "Worldwide (remoto)"

    employment_type = _EMPLOYMENT_MAP.get(raw.get("employmentType") or "", parsed["employment_type"])

    seniority_list = raw.get("seniority") or []
    seniority = parsed["seniority"]
    if seniority_list:
        seniority = _SENIORITY_MAP.get(seniority_list[0], seniority_list[0].lower())

    # Himalayas' own categories are a reliable extra signal beyond the
    # free-text skill scan (e.g. "React", "DevOps") — add any not already
    # picked up, tagged as nice-to-have since they're topical, not verified
    # "required" skills the way a requirements-section hit is.
    known = {s["name"].lower() for s in parsed["skills_required"]}
    categories = (raw.get("categories") or []) + (raw.get("parentCategories") or [])
    extra_skills = [
        {"name": c, "importance": "nice_to_have"}
        for c in dict.fromkeys(categories)  # de-dupe, keep order
        if c and c.lower() not in known
    ]

    posted_at = None
    pub_date = raw.get("pubDate")
    if isinstance(pub_date, (int, float)):
        try:
            posted_at = datetime.fromtimestamp(pub_date, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            posted_at = None

    return {
        "himalayas_job_id": raw.get("guid"),
        "source": "himalayas",
        "source_url": raw.get("applicationLink"),
        "title": title,
        "company": company,
        "location": location,
        "remote_type": "remote",
        "employment_type": employment_type,
        "seniority": seniority,
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"] + extra_skills,
        "salary_min": raw.get("minSalary"),
        "salary_max": raw.get("maxSalary"),
        "salary_currency": raw.get("currency"),
        "salary_period": raw.get("salaryPeriod") or "annual",
        "posted_at": posted_at,
        "categories": categories,
        "timezone_restrictions": raw.get("timezoneRestrictions") or [],
        "company_logo": raw.get("companyLogo"),
    }


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def search_himalayas_jobs(
    q: Optional[str] = None,
    country: Optional[str] = None,
    worldwide: Optional[bool] = None,
    exclude_worldwide: Optional[bool] = None,
    seniority: Optional[str] = None,
    employment_type: Optional[str] = None,
    company: Optional[str] = None,
    timezone_filter: Optional[str] = None,
    sort: Optional[str] = None,
    page: int = 1,
) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page}
    if q:
        params["q"] = q
    if country:
        params["country"] = country
    if worldwide is not None:
        params["worldwide"] = str(worldwide).lower()
    if exclude_worldwide is not None:
        params["exclude_worldwide"] = str(exclude_worldwide).lower()
    if seniority:
        params["seniority"] = seniority
    if employment_type:
        params["employment_type"] = employment_type
    if company:
        params["company"] = company
    if timezone_filter:
        params["timezone"] = timezone_filter
    if sort:
        params["sort"] = sort

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(HIMALAYAS_SEARCH_ENDPOINT, params=params)
    except httpx.HTTPError as exc:
        raise HimalayasError("Could not reach Himalayas (network error).") from exc

    if resp.status_code != 200:
        raise HimalayasError(f"Himalayas request failed with status {resp.status_code}.")

    try:
        data = resp.json()
    except ValueError as exc:
        raise HimalayasError("Himalayas returned a non-JSON response.") from exc

    now = time.time()
    results = []
    for raw in data.get("jobs", []) or []:
        normalized = _normalize(raw)
        if normalized["himalayas_job_id"]:
            _search_cache[normalized["himalayas_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    return {
        "results": results,
        "total_count": data.get("totalCount"),
        "page": page,
        "has_more": len(results) > 0,
    }


def get_cached_result(himalayas_job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(himalayas_job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(himalayas_job_id, None)
        return None
    return entry["job"]
