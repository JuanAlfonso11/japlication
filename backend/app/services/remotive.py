"""Remotive Remote Jobs API — free, no API key.
Docs: https://remotive.com/api/remote-jobs (mirrored at
https://github.com/remotive-com/remote-jobs-api)

Remotive's terms are stricter than the other free sources: max ~2 requests/
minute, and results must visibly attribute Remotive as the source (handled
in the frontend result card, not here) and must not be re-published to
other job aggregators. This module makes exactly one request per search
call and relies on the shared short-lived cache to avoid hammering it.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

import httpx

from app.services.external_jobs import http as external_http

from app.services import experience_level
from app.services.job_importer import html_to_text, parse_job_text_heuristic

ENDPOINT = "https://remotive.com/api/remote-jobs"
_CACHE_TTL_SECONDS = 15 * 60
_search_cache: dict[str, dict[str, Any]] = {}


class RemotiveError(RuntimeError):
    pass


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    title = raw.get("title") or "Untitled position"
    company = raw.get("company_name") or "Unknown company"
    description = html_to_text(raw.get("description") or "").strip() or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    job_type = str(raw.get("job_type") or "")
    employment_type = {
        "full_time": "full_time",
        "part_time": "part_time",
        "contract": "contract",
        "freelance": "contract",
        "internship": "internship",
    }.get(job_type, parsed["employment_type"])

    level = "internship" if job_type == "internship" else experience_level.infer(title, description)

    posted_at = None
    pub_date = raw.get("publication_date")
    if pub_date:
        try:
            posted_at = datetime.fromisoformat(str(pub_date).replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    salary_min = salary_max = salary_currency = None
    salary_text = raw.get("salary")
    if isinstance(salary_text, str) and salary_text.strip():
        import re

        nums = re.findall(r"[\d,]+", salary_text)
        values = [float(n.replace(",", "")) for n in nums[:2] if n.replace(",", "").isdigit()]
        if values:
            salary_min, salary_max = min(values), max(values)
            if "$" in salary_text:
                salary_currency = "USD"

    return {
        "remotive_job_id": str(raw.get("id")) if raw.get("id") is not None else None,
        "source": "remotive",
        "source_url": raw.get("url"),
        "title": title,
        "company": company,
        "location": raw.get("candidate_required_location") or "Worldwide (remote)",
        "remote_type": "remote",
        "employment_type": employment_type,
        "seniority": level,
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"],
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": salary_currency,
        "posted_at": posted_at,
        "category": raw.get("category"),
    }


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def search_remotive_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 40,
) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": limit}
    if q:
        params["search"] = q
    if category:
        params["category"] = category

    try:
        resp = await external_http.get("remotive", ENDPOINT, params=params)
    except httpx.HTTPError as exc:
        raise RemotiveError("Could not reach Remotive (network error).") from exc

    if resp.status_code != 200:
        raise RemotiveError(f"Remotive request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise RemotiveError("Remotive returned a non-JSON response.") from exc

    now = time.time()
    results = []
    for raw in data.get("jobs", []) or []:
        normalized = _normalize(raw)

        loc = (location or "").strip().lower()
        if loc and loc not in ("worldwide", "remote", "remoto"):
            if loc not in (normalized["location"] or "").lower():
                continue
        if remote_type_filter and normalized["remote_type"] and normalized["remote_type"] != remote_type_filter:
            continue
        if not experience_level.matches(normalized["seniority"], experience_level_filter):
            continue

        if normalized["remotive_job_id"]:
            _search_cache[normalized["remotive_job_id"]] = {"cached_at": now, "job": normalized}
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
