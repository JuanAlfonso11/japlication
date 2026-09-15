"""SerpApi's Google Jobs engine — free registered key, self-serve instant
signup at https://serpapi.com/users/sign_up (250 searches/month free, 50/hr).
Docs: https://serpapi.com/google-jobs-api

Google for Jobs aggregates postings crawled from many job sites' own
public, crawlable pages (LinkedIn, Indeed, Glassdoor, ZipRecruiter, and
plenty of smaller boards) — this reaches LinkedIn-hosted postings that
LinkedIn itself allows Google to index, without ever touching linkedin.com
or a LinkedIn account. `via` on each result names which site it actually
came from.

No pagination support (Google Jobs paginates via an opaque
`next_page_token` rather than a page number, unlike every other provider
here) — same simplification several of the no-auth providers already make
(Remotive, Jobicy, We Work Remotely, Hacker News all just return
has_more=False too), so this isn't a new pattern for the router to learn.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.services.external_jobs import http as external_http

from app.core.config import settings
from app.services import experience_level
from app.services.job_importer import html_to_text, parse_job_text_heuristic

ENDPOINT = "https://serpapi.com/search.json"
_CACHE_TTL_SECONDS = 15 * 60
_search_cache: dict[str, dict[str, Any]] = {}

_EMPLOYMENT_TYPE_MAP = {
    "full-time": "full_time",
    "part-time": "part_time",
    "contract": "contract",
    "contractor": "contract",
    "internship": "internship",
    "temp": "contract",
    "temporary": "contract",
}

_REQUIREMENTS_SECTIONS = {"qualifications", "requirements", "minimum qualifications", "what you'll need"}
_RESPONSIBILITIES_SECTIONS = {"responsibilities", "role", "duties", "what you'll do"}

_RELATIVE_POSTED_RE = re.compile(r"(\d+)\+?\s*(minute|hour|day|week|month)s?\s+ago", re.IGNORECASE)


class SerpApiError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.SERPAPI_API_KEY)


def _parse_relative_posted_at(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    lowered = text.strip().lower()
    now = datetime.now(timezone.utc)
    if lowered == "today":
        return now
    if lowered == "yesterday":
        return now - timedelta(days=1)
    match = _RELATIVE_POSTED_RE.search(lowered)
    if not match:
        return None
    n = int(match.group(1))
    unit = match.group(2)
    delta = {
        "minute": timedelta(minutes=n),
        "hour": timedelta(hours=n),
        "day": timedelta(days=n),
        "week": timedelta(weeks=n),
        "month": timedelta(days=30 * n),
    }.get(unit)
    return now - delta if delta else None


def _parse_salary(text: Optional[str]) -> tuple[Optional[float], Optional[float], Optional[str]]:
    if not text:
        return None, None, None
    k_matches = re.findall(r"(\d+(?:\.\d+)?)\s*[Kk]", text)
    if k_matches:
        values = [float(v) * 1000 for v in k_matches[:2]]
    else:
        plain = re.findall(r"[\d,]+(?:\.\d+)?", text)
        values = [float(v.replace(",", "")) for v in plain[:2] if v.replace(",", "").replace(".", "").isdigit()]
    if not values:
        return None, None, None
    currency = "USD" if "$" in text else None
    return min(values), max(values), currency


def _extract_highlight_sections(job_highlights: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    requirements: list[str] = []
    responsibilities: list[str] = []
    for section in job_highlights or []:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or "").strip().lower()
        items = [i for i in (section.get("items") or []) if isinstance(i, str) and i.strip()]
        if title in _REQUIREMENTS_SECTIONS:
            requirements.extend(items)
        elif title in _RESPONSIBILITIES_SECTIONS:
            responsibilities.extend(items)
    return requirements, responsibilities


def _normalize(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    job_id = raw.get("job_id")
    title = raw.get("title") or raw.get("job_title")
    if not job_id or not title:
        return None

    company = raw.get("company_name") or "Unknown company"
    description = (raw.get("description") or "").strip() or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    detected = raw.get("detected_extensions") or {}
    employment_type = _EMPLOYMENT_TYPE_MAP.get(
        str(detected.get("schedule_type") or "").strip().lower(), parsed["employment_type"]
    )

    location = raw.get("location")
    if detected.get("work_from_home") is True:
        remote_type = "remote"
    elif location and "anywhere" in location.lower():
        remote_type = "remote"
    else:
        remote_type = parsed.get("remote_type")

    level = experience_level.infer(title, description) or parsed.get("seniority")

    requirements, responsibilities = _extract_highlight_sections(raw.get("job_highlights") or [])
    if not requirements:
        requirements = parsed["requirements"]
    if not responsibilities:
        responsibilities = parsed["responsibilities"]

    salary_min, salary_max, salary_currency = _parse_salary(detected.get("salary"))
    posted_at_text = detected.get("posted_at")
    posted_at = _parse_relative_posted_at(posted_at_text)

    source_url = raw.get("source_link")
    if not source_url:
        apply_options = raw.get("apply_options") or []
        source_url = apply_options[0].get("link") if apply_options and isinstance(apply_options[0], dict) else None
    source_url = source_url or raw.get("share_link")

    return {
        "serpapi_job_id": str(job_id),
        "source": "serpapi",
        "source_url": source_url,
        "title": title,
        "company": company,
        "location": location,
        "remote_type": remote_type,
        "employment_type": employment_type,
        "seniority": level,
        "description": html_to_text(description) or description,
        "requirements": requirements,
        "responsibilities": responsibilities,
        "skills_required": parsed["skills_required"],
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": salary_currency,
        "posted_at": posted_at,
        "posted_at_text": posted_at_text,
        "via": raw.get("via"),
    }


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def search_serpapi_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
) -> dict[str, Any]:
    if not is_configured():
        raise SerpApiError("SerpApi is not configured (missing SERPAPI_API_KEY).")

    params: dict[str, Any] = {
        "engine": "google_jobs",
        "api_key": settings.SERPAPI_API_KEY,
        "hl": "en",
        "q": q.strip() if q and q.strip() else "remote jobs",
    }
    if location:
        params["location"] = location

    try:
        resp = await external_http.get("serpapi", ENDPOINT, params=params)
    except httpx.HTTPError as exc:
        raise SerpApiError("Could not reach SerpApi (network error).") from exc

    if resp.status_code != 200:
        raise SerpApiError(f"SerpApi request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise SerpApiError("SerpApi returned a non-JSON response.") from exc

    if data.get("error"):
        raise SerpApiError(f"SerpApi error: {data['error']}")

    now = time.time()
    results = []
    for raw in data.get("jobs_results", []) or []:
        normalized = _normalize(raw)
        if normalized is None:
            continue

        loc = (location or "").strip().lower()
        if loc and loc not in ("worldwide", "remote", "remoto", "anywhere"):
            if loc not in (normalized["location"] or "").lower():
                continue
        if remote_type_filter and normalized["remote_type"] and normalized["remote_type"] != remote_type_filter:
            continue
        if not experience_level.matches(normalized["seniority"], experience_level_filter):
            continue

        _search_cache[normalized["serpapi_job_id"]] = {"cached_at": now, "job": normalized}
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
