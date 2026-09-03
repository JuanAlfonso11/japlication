"""Live job search via SerpApi's Google Jobs engine
(https://serpapi.com/search?engine=google_jobs).

This is a *search* surface, distinct from `job_importer.py` (which fetches
and parses one already-known URL): it queries Google Jobs for a keyword +
location and returns normalized, ready-to-preview results. Nothing is
persisted to the `jobs` table until the caller explicitly imports one result
(`POST /jobs/search/import`), at which point we reuse the same heuristic
extraction (`parse_job_text_heuristic`) and skills taxonomy already used by
the URL importer, so a Google Jobs result becomes a `Job` row shaped exactly
like any other source.

SerpApi is a metered third-party API, so search results for a given
`google_job_id` are cached in-process for a short TTL: the import step reuses
that cached result instead of re-querying SerpApi, and rejects an unknown/
expired id by asking the caller to search again. This keeps a single search
request paid for once. The cache is per-process, in-memory — correct for a
single-worker personal deployment; a multi-worker/multi-instance deployment
would need a shared cache (e.g. Redis) instead.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.services.job_importer import parse_job_text_heuristic

SERPAPI_ENDPOINT = "https://serpapi.com/search"
_CACHE_TTL_SECONDS = 15 * 60

# google_job_id -> {"cached_at": float, "job": {...normalized...}}
_search_cache: dict[str, dict[str, Any]] = {}


class GoogleJobsError(RuntimeError):
    """Raised for any condition that should surface as a clean HTTP error
    (missing API key, upstream failure, upstream-reported error)."""


_RELATIVE_POSTED_RE = re.compile(
    r"(\d+)\s*\+?\s*(hour|hora|day|d[ií]a|week|semana|month|mes)", re.IGNORECASE
)
_UNIT_TO_TIMEDELTA = {
    "hour": lambda n: timedelta(hours=n),
    "hora": lambda n: timedelta(hours=n),
    "day": lambda n: timedelta(days=n),
    "dia": lambda n: timedelta(days=n),
    "día": lambda n: timedelta(days=n),
    "week": lambda n: timedelta(weeks=n),
    "semana": lambda n: timedelta(weeks=n),
    "month": lambda n: timedelta(days=30 * n),
    "mes": lambda n: timedelta(days=30 * n),
}


def _parse_relative_posted_at(text: Optional[str]) -> Optional[datetime]:
    """SerpApi reports `posted_at` as relative text ("3 days ago", "hace 2
    días"), not an absolute date. Best-effort convert it to an absolute UTC
    timestamp; return None when the text doesn't match a known pattern."""
    if not text:
        return None
    match = _RELATIVE_POSTED_RE.search(text)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    delta_fn = _UNIT_TO_TIMEDELTA.get(unit)
    if delta_fn is None:
        return None
    return datetime.now(timezone.utc) - delta_fn(amount)


# Each number token with an optional immediate "K"/"k" suffix (e.g. "110K",
# "137,000"); the multiplier is applied per-token so "$110K–$140K" and
# "$90,000–$120K" (mixed) both parse correctly.
_SALARY_TOKEN_RE = re.compile(r"(\d[\d,.]*)\s*([kK])?")


def _parse_salary(detected: dict[str, Any]) -> tuple[Optional[float], Optional[float], Optional[str]]:
    salary = detected.get("salary")
    if not salary or not isinstance(salary, str):
        return None, None, None

    currency = None
    if "$" in salary:
        currency = "USD"
    elif "€" in salary:
        currency = "EUR"
    elif "£" in salary:
        currency = "GBP"

    values: list[float] = []
    for num, k in _SALARY_TOKEN_RE.findall(salary):
        if not num:
            continue
        value = float(num.replace(",", ""))
        if k:
            value *= 1000.0
        values.append(value)
        if len(values) == 2:
            break

    if not values:
        return None, None, currency
    if len(values) == 1:
        return values[0], values[0], currency
    return min(values), max(values), currency


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    detected = raw.get("detected_extensions") or {}
    apply_options_raw = raw.get("apply_options") or []
    apply_options = [
        {"title": o.get("title") or "Apply", "link": o.get("link")}
        for o in apply_options_raw
        if o.get("link")
    ]
    source_url = apply_options[0]["link"] if apply_options else raw.get("share_link")

    title = raw.get("title") or "Untitled position"
    company = raw.get("company_name") or "Unknown company"
    description = (raw.get("description") or "").strip() or "No description provided."

    # Reuse the same heuristic extractor the URL importer uses for
    # requirements/responsibilities/skills — SerpApi gives us clean plain-text
    # descriptions, so the text-based heuristics apply directly.
    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    schedule_type = detected.get("schedule_type")
    employment_type = parsed["employment_type"]
    if isinstance(schedule_type, str):
        normalized_schedule = schedule_type.strip().lower().replace("-", " ")
        employment_type = {
            "full time": "full_time",
            "part time": "part_time",
            "contractor": "contract",
            "internship": "internship",
        }.get(normalized_schedule, employment_type)

    remote_type = parsed["remote_type"]
    if detected.get("work_from_home"):
        remote_type = "remote"

    salary_min, salary_max, salary_currency = _parse_salary(detected)
    posted_at = _parse_relative_posted_at(detected.get("posted_at"))

    google_job_id = raw.get("job_id")

    normalized = {
        "google_job_id": google_job_id,
        "source": "google_jobs",
        "source_url": source_url,
        "title": title,
        "company": company,
        "location": raw.get("location") or parsed["location"],
        "remote_type": remote_type,
        "employment_type": employment_type,
        "seniority": parsed["seniority"],
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"],
        "salary_min": salary_min if salary_min is not None else parsed["salary_min"],
        "salary_max": salary_max if salary_max is not None else parsed["salary_max"],
        "salary_currency": salary_currency or parsed["salary_currency"],
        "posted_at": posted_at,
        "posted_at_text": detected.get("posted_at"),
        "via": raw.get("via"),
        "extensions": raw.get("extensions") or [],
        "apply_options": apply_options,
        "thumbnail": raw.get("thumbnail"),
    }
    return normalized


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def search_google_jobs(
    q: str,
    location: Optional[str] = None,
    hl: Optional[str] = None,
    gl: Optional[str] = None,
    next_page_token: Optional[str] = None,
) -> dict[str, Any]:
    if not settings.SERPAPI_API_KEY:
        raise GoogleJobsError(
            "SERPAPI_API_KEY is not configured. Get a key at https://serpapi.com and set it "
            "in the backend's .env to enable Google Jobs search."
        )

    params: dict[str, str] = {
        "engine": "google_jobs",
        "q": q,
        "hl": hl or settings.SERPAPI_DEFAULT_HL,
        "gl": gl or settings.SERPAPI_DEFAULT_GL,
        "api_key": settings.SERPAPI_API_KEY,
    }
    if location:
        params["location"] = location
    if next_page_token:
        params["next_page_token"] = next_page_token

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(SERPAPI_ENDPOINT, params=params)
    except httpx.HTTPError as exc:
        raise GoogleJobsError("Could not reach SerpApi (network error).") from exc

    if resp.status_code != 200:
        raise GoogleJobsError(f"SerpApi request failed with status {resp.status_code}.")

    try:
        data = resp.json()
    except ValueError as exc:
        raise GoogleJobsError("SerpApi returned a non-JSON response.") from exc

    if data.get("error"):
        raise GoogleJobsError(str(data["error"]))

    now = time.time()
    results = []
    for raw in data.get("jobs_results", []) or []:
        normalized = _normalize(raw)
        if normalized["google_job_id"]:
            _search_cache[normalized["google_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    pagination = data.get("serpapi_pagination") or {}
    return {"results": results, "next_page_token": pagination.get("next_page_token")}


def get_cached_result(google_job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(google_job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(google_job_id, None)
        return None
    return entry["job"]
