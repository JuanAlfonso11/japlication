"""Adzuna Jobs API — free registered key (app_id + app_key), instant
self-serve signup at https://developer.adzuna.com/. Free tier: 1,000
calls/month. Docs: https://developer.adzuna.com/docs/search

Unlike the no-auth providers, Adzuna has no single global endpoint —
search is per-country (GET /v1/api/jobs/{country}/search/{page}).
`country` defaults to "us" (Adzuna's largest market) whenever the
caller's location doesn't map to one of Adzuna's ~20 supported
countries — see _COUNTRY_SLUGS.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

import httpx

from app.services.external_jobs import http as external_http

from app.core.config import settings
from app.services import experience_level
from app.services.job_importer import html_to_text, parse_job_text_heuristic

BASE_URL = "https://api.adzuna.com/v1/api/jobs"
_CACHE_TTL_SECONDS = 15 * 60
_search_cache: dict[str, dict[str, Any]] = {}

_COUNTRY_SLUGS = {
    "united states": "us", "usa": "us", "us": "us",
    "united kingdom": "gb", "uk": "gb", "gb": "gb",
    "canada": "ca",
    "germany": "de",
    "france": "fr",
    "spain": "es",
    "australia": "au",
    "mexico": "mx",
    "brazil": "br",
    "india": "in",
    "italy": "it",
    "netherlands": "nl",
    "poland": "pl",
    "new zealand": "nz",
    "singapore": "sg",
    "south africa": "za",
    "switzerland": "ch",
    "austria": "at",
    "belgium": "be",
}

_CURRENCY_BY_COUNTRY = {
    "us": "USD", "gb": "GBP", "ca": "CAD", "de": "EUR", "fr": "EUR", "es": "EUR",
    "au": "AUD", "mx": "MXN", "br": "BRL", "in": "INR", "it": "EUR", "nl": "EUR",
    "pl": "PLN", "nz": "NZD", "sg": "SGD", "za": "ZAR", "ch": "CHF", "at": "EUR",
    "be": "EUR",
}

_EMPLOYMENT_TYPE_MAP = {"full_time": "full_time", "part_time": "part_time"}


class AdzunaError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.ADZUNA_APP_ID and settings.ADZUNA_APP_KEY)


def country_slug(location: Optional[str]) -> str:
    if not location:
        return "us"
    return _COUNTRY_SLUGS.get(location.strip().lower(), "us")


def _normalize(raw: dict[str, Any], country: str) -> dict[str, Any]:
    title = raw.get("title") or "Untitled position"
    company = (raw.get("company") or {}).get("display_name") or "Unknown company"
    description = html_to_text(raw.get("description") or "").strip() or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    contract_time = raw.get("contract_time")
    contract_type = raw.get("contract_type")
    employment_type = _EMPLOYMENT_TYPE_MAP.get(contract_time or "")
    if not employment_type and contract_type == "contract":
        employment_type = "contract"
    employment_type = employment_type or parsed["employment_type"]

    level = experience_level.infer(title, description) or parsed.get("seniority")

    posted_at = None
    created = raw.get("created")
    if created:
        try:
            posted_at = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    location_name = (raw.get("location") or {}).get("display_name")

    remote_type = parsed.get("remote_type")
    if remote_type is None and "remote" in f"{title} {location_name or ''}".lower():
        remote_type = "remote"

    salary_min = raw.get("salary_min")
    salary_max = raw.get("salary_max")

    return {
        "adzuna_job_id": str(raw.get("id")) if raw.get("id") is not None else None,
        "source": "adzuna",
        "source_url": raw.get("redirect_url"),
        "title": title,
        "company": company,
        "location": location_name,
        "remote_type": remote_type,
        "employment_type": employment_type,
        "seniority": level,
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"],
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": _CURRENCY_BY_COUNTRY.get(country) if (salary_min or salary_max) else None,
        "posted_at": posted_at,
        "category": (raw.get("category") or {}).get("label"),
    }


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def search_adzuna_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
    country: Optional[str] = None,
    page: int = 1,
    results_per_page: int = 20,
) -> dict[str, Any]:
    if not is_configured():
        raise AdzunaError("Adzuna is not configured (missing ADZUNA_APP_ID/ADZUNA_APP_KEY).")

    resolved_country = country or country_slug(location)
    params: dict[str, Any] = {
        "app_id": settings.ADZUNA_APP_ID,
        "app_key": settings.ADZUNA_APP_KEY,
        "results_per_page": results_per_page,
        "content-type": "application/json",
    }
    if q:
        params["what"] = q
    if location:
        params["where"] = location

    try:
        resp = await external_http.get("adzuna", f"{BASE_URL}/{resolved_country}/search/{page}", params=params)
    except httpx.HTTPError as exc:
        raise AdzunaError("Could not reach Adzuna (network error).") from exc

    if resp.status_code != 200:
        raise AdzunaError(f"Adzuna request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise AdzunaError("Adzuna returned a non-JSON response.") from exc

    now = time.time()
    results = []
    raw_results = data.get("results", []) or []
    for raw in raw_results:
        normalized = _normalize(raw, resolved_country)
        if remote_type_filter and normalized["remote_type"] and normalized["remote_type"] != remote_type_filter:
            continue
        if not experience_level.matches(normalized["seniority"], experience_level_filter):
            continue
        if normalized["adzuna_job_id"]:
            _search_cache[normalized["adzuna_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    has_more = len(raw_results) >= results_per_page
    return {"results": results, "has_more": has_more}


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
