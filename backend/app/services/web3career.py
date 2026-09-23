"""Web3.career — Web3/crypto job board API. Free token, requested from
https://web3.career/web3-jobs-api (WEB3CAREER_TOKEN in .env).

Verified live 2026-09-23. The response is a 3-element list, not an object:
`["Web3 Jobs API https://web3.career", "<help text>", [jobs...]]`.
Params: `tag` (one slug, e.g. "react"), `remote=true`, `country=<slug>`,
`limit` (max 100), `show_description`. There is no free-text search, so `q`
is sent as a tag.

Terms (in the help text itself): link back using `apply_url`, unmodified,
and name web3.career as the source, or access is suspended. So `source_url`
is always `apply_url` untouched, and Discover shows the provider name on
each card.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.services import experience_level
from app.services.external_jobs import http as external_http
from app.services.job_importer import html_to_text, parse_job_text_heuristic

API_URL = "https://web3.career/api/v1"
_CACHE_TTL_SECONDS = 60 * 60

_response_cache: dict[tuple, dict[str, Any]] = {}
_search_cache: dict[str, dict[str, Any]] = {}

#: Discover's location values that mean "anywhere" rather than a country.
_NOT_A_COUNTRY = {"remote", "remoto", "worldwide", "anywhere", "latin america", "europe"}


class Web3CareerError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.WEB3CAREER_TOKEN)


def _tag(q: Optional[str]) -> Optional[str]:
    q = (q or "").strip().lower()
    return "-".join(q.split()) or None


def _country(location: Optional[str]) -> Optional[str]:
    loc = (location or "").strip().lower()
    if not loc or loc in _NOT_A_COUNTRY:
        return None
    return "-".join(loc.split())


def _normalize(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    job_id = raw.get("id")
    apply_url = raw.get("apply_url")
    if job_id is None or not apply_url:
        return None

    title = raw.get("title") or "Untitled position"
    company = raw.get("company") or "Unknown company"
    description = html_to_text(raw.get("description") or "").strip() or title
    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    posted_at = None
    if raw.get("date_epoch"):
        try:
            posted_at = datetime.fromtimestamp(int(raw["date_epoch"]), tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            posted_at = None

    # Only the employer's own numbers; `estimated_*_salary` is web3.career's guess.
    salary_min = raw.get("salary_min_value")
    salary_max = raw.get("salary_max_value")

    tags = [t for t in (raw.get("tags") or []) if isinstance(t, str)]
    skills = parsed["skills_required"] or [{"name": t, "importance": "required"} for t in tags if t != "remote"]

    return {
        "web3career_job_id": str(job_id),
        "source": "web3career",
        "source_url": apply_url,
        "title": title,
        "company": company,
        "location": (raw.get("location") or "").strip() or "Remote",
        "remote_type": "remote" if raw.get("is_remote") else (parsed.get("remote_type") or "onsite"),
        "employment_type": parsed["employment_type"],
        "seniority": experience_level.infer(title, description) or parsed["seniority"],
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": skills,
        "salary_min": float(salary_min) if salary_min else None,
        "salary_max": float(salary_max) if salary_max else None,
        "salary_currency": raw.get("salary_currency") if (salary_min or salary_max) else None,
        "posted_at": posted_at,
    }


async def _fetch(tag: Optional[str], remote: bool, country: Optional[str]) -> list[dict[str, Any]]:
    key = (tag, remote, country)
    now = time.time()
    cached = _response_cache.get(key)
    if cached and now - cached["fetched_at"] < _CACHE_TTL_SECONDS:
        return cached["jobs"]

    params: dict[str, Any] = {"token": settings.WEB3CAREER_TOKEN, "limit": 100}
    if tag:
        params["tag"] = tag
    if remote:
        params["remote"] = "true"
    if country:
        params["country"] = country

    try:
        resp = await external_http.get("web3career", API_URL, params=params)
    except httpx.HTTPError as exc:
        raise Web3CareerError("Could not reach Web3.career (network error).") from exc
    if resp.status_code != 200:
        raise Web3CareerError(f"Web3.career request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        # A bad token answers 200 with an HTML page, not JSON.
        raise Web3CareerError("Web3.career returned a non-JSON response (check WEB3CAREER_TOKEN).") from exc
    if not (isinstance(data, list) and len(data) >= 3 and isinstance(data[2], list)):
        raise Web3CareerError("Web3.career returned an unexpected response shape.")

    jobs = [j for j in (_normalize(r) for r in data[2] if isinstance(r, dict)) if j]
    _response_cache[key] = {"jobs": jobs, "fetched_at": now}
    return jobs


async def search_web3career_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
) -> dict[str, Any]:
    if not is_configured():
        raise Web3CareerError("Web3.career is not configured (missing WEB3CAREER_TOKEN).")

    jobs = await _fetch(_tag(q), remote_type_filter == "remote", _country(location))

    now = time.time()
    results = []
    for job in jobs:
        if remote_type_filter and job["remote_type"] != remote_type_filter:
            continue
        if not experience_level.matches(job["seniority"], experience_level_filter):
            continue
        _search_cache[job["web3career_job_id"]] = {"cached_at": now, "job": job}
        results.append(job)
    _cleanup_cache(now)

    return {"results": results, "has_more": False}


def _cleanup_cache(now: float) -> None:
    for k in [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]:
        _search_cache.pop(k, None)
    for k in [k for k, v in _response_cache.items() if now - v["fetched_at"] > _CACHE_TTL_SECONDS]:
        _response_cache.pop(k, None)


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
