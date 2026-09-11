"""LinkedIn job search through Bright Data's LinkedIn job listings dataset.

LinkedIn offers no job search API a personal app can get (see
docs/PUBLIC_APIS_RESEARCH.md). Bright Data runs the search on LinkedIn's
public, logged-out job pages and returns structured records, so no LinkedIn
account is involved and none can be restricted for it. It is paid per
record, which shapes everything below.

WHY RESULTS ARRIVE ON THE SECOND SEARCH
A discovery run takes 45-90 seconds (trigger, then poll until the snapshot is
ready), and Discover waits for every source at once — waiting on LinkedIn
would stall the other fourteen. So this is stale-while-revalidate: a search
answers from a per-query cache immediately, and a cache miss starts the run
in the background and reports LinkedInPending for this source. Searching
again a minute later shows the postings. The every-2-hours sweep keeps the
profile's own query warm.

COST CONTROLS
- Results are cached per (keyword, location, work type) for six hours, so a
  repeated search never pays twice.
- api_budget caps real Bright Data runs per day. The budget is consumed here,
  right before a run, not by the router on every search: a cache hit costs
  nothing and must not use up the day's allowance.
- Each run asks for at most MAX_RECORDS postings from the past week.
- No keyword, no run: an empty search returns nothing instead of paying for a
  generic query.
- A run that just failed is reported for a few minutes instead of retried, so
  a broken configuration cannot quietly spend the daily budget.

THE REMOTE TAG
LinkedIn applies its own workplace-type filter ("Remote"/"Hybrid"/"On-site")
at search time. That is the structured value the employer set, so a posting
from a filtered search carries the requested type — the records have no
work-type field of their own to read it back from. Two exceptions: a title
that states its own work type wins (a "Hybrid" posting that slipped into a
remote search is tagged hybrid and filtered out), and a search with no
work-type filter falls back to the description keyword scan every other
source uses.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.services import api_budget, experience_level
from app.services.job_importer import _extract_remote_type, html_to_text, parse_job_text_heuristic

logger = logging.getLogger(__name__)

API = "https://api.brightdata.com/datasets/v3"
DATASET_ID = "gd_lpfll7v5hcqtkxl6l"
MAX_RECORDS = 10
_RESULTS_TTL_SECONDS = 6 * 60 * 60
_FAILURE_TTL_SECONDS = 10 * 60
_POLL_INTERVAL_SECONDS = 10
_POLL_DEADLINE_SECONDS = 5 * 60

_WORK_TYPES = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "On-site"}
_EMPLOYMENT_TYPES = {
    "full-time": "full_time",
    "part-time": "part_time",
    "contract": "contract",
    "temporary": "contract",
    "internship": "internship",
}
_SENIORITY = {
    "internship": "internship",
    "entry level": "entry",
    "associate": "mid",
    "mid-senior level": "senior",
    "director": "lead",
    "executive": "lead",
}

Key = tuple[str, str, str]  # (keyword, location, work type)

# ponytail: in-process caches for a single uvicorn worker — lost on restart and
# not shared between workers. Move to Redis or a table if the backend ever runs
# more than one process.
_query_cache: dict[Key, dict[str, Any]] = {}
_job_cache: dict[str, dict[str, Any]] = {}
_failures: dict[Key, tuple[float, str]] = {}
_in_flight: dict[Key, asyncio.Task] = {}


class LinkedInError(RuntimeError):
    pass


class LinkedInPending(LinkedInError):
    """A background run is still collecting results. Discover shows this as
    "buscando…" rather than as a failure — its message must keep the words
    "segundo plano", which is what the frontend keys on."""


def is_configured() -> bool:
    return bool(settings.BRIGHTDATA_API_KEY)


def _posted_at(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize(raw: dict[str, Any], requested_work_type: Optional[str]) -> Optional[dict[str, Any]]:
    job_id = raw.get("job_posting_id")
    title = str(raw.get("job_title") or "").strip()
    if not job_id or not title or raw.get("error"):
        return None

    company = raw.get("company_name") or "Unknown company"
    description = (
        str(raw.get("job_summary") or "").strip()
        or html_to_text(raw.get("job_description_formatted") or "")
        or "No description provided."
    )
    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    return {
        "linkedin_job_id": str(job_id),
        "source": "linkedin",
        # The job page rather than apply_link, which is empty on most records;
        # the page is where LinkedIn's "Apply" lives anyway. The query string
        # is LinkedIn's own tracking.
        "source_url": str(raw.get("url") or "").split("?", 1)[0] or None,
        "title": title,
        "company": company,
        "location": raw.get("job_location"),
        # See THE REMOTE TAG in the module docstring.
        "remote_type": _extract_remote_type(title) or requested_work_type or _extract_remote_type(description),
        "employment_type": _EMPLOYMENT_TYPES.get(
            str(raw.get("job_employment_type") or "").strip().lower(), parsed["employment_type"]
        ),
        "seniority": _SENIORITY.get(str(raw.get("job_seniority_level") or "").strip().lower())
        or experience_level.infer(title, description),
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"],
        # ponytail: base_salary was empty on every record sampled; parse it when one shows up.
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "posted_at": _posted_at(raw.get("job_posted_date")),
        "posted_at_text": raw.get("job_posted_time"),
        "via": "LinkedIn",
    }


async def _run_discovery(key: Key) -> list[dict[str, Any]]:
    keyword, location, work_type = key
    payload = [
        {
            "keyword": keyword,
            "location": location,
            "country": "",
            "time_range": "Past week",
            "job_type": "",
            "experience_level": "",
            "remote": _WORK_TYPES.get(work_type, ""),
            "company": "",
            "location_radius": "",
        }
    ]
    params = {
        "dataset_id": DATASET_ID,
        "type": "discover_new",
        "discover_by": "keyword",
        "include_errors": "true",
        "limit_per_input": MAX_RECORDS,
    }
    headers = {"Authorization": f"Bearer {settings.BRIGHTDATA_API_KEY}"}
    try:
        async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30.0) as client:
            resp = await client.post("/trigger", params=params, json=payload)
            if resp.status_code != 200:
                raise LinkedInError(f"Bright Data rechazó la búsqueda ({resp.status_code}): {resp.text[:120]}")
            snapshot = resp.json().get("snapshot_id")
            if not snapshot:
                raise LinkedInError("Bright Data no devolvió un snapshot_id.")

            deadline = time.monotonic() + _POLL_DEADLINE_SECONDS
            while True:
                status = (await client.get(f"/progress/{snapshot}")).json().get("status")
                if status == "ready":
                    break
                if status == "failed":
                    raise LinkedInError("La búsqueda en LinkedIn falló en Bright Data.")
                if time.monotonic() > deadline:
                    raise LinkedInError("LinkedIn tardó demasiado en responder.")
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)

            data = (await client.get(f"/snapshot/{snapshot}", params={"format": "json"})).json()
    except httpx.HTTPError as exc:
        raise LinkedInError("No se pudo contactar a Bright Data.") from exc

    if not isinstance(data, list):
        raise LinkedInError("Bright Data devolvió una respuesta inesperada.")
    return data


async def _refresh(key: Key) -> None:
    """Background run for one query. Records its outcome in the caches and
    never raises: nothing awaits this task, so an exception would vanish."""
    try:
        records = await _run_discovery(key)
        now = time.time()
        jobs = [job for job in (_normalize(r, key[2] or None) for r in records if isinstance(r, dict)) if job]
        _query_cache[key] = {"cached_at": now, "results": jobs}
        for stale_id in [j for j, e in _job_cache.items() if now - e["cached_at"] > _RESULTS_TTL_SECONDS]:
            _job_cache.pop(stale_id, None)
        for job in jobs:
            _job_cache[job["linkedin_job_id"]] = {"cached_at": now, "job": job}
        _failures.pop(key, None)
    except Exception as exc:  # noqa: BLE001 — recorded for the next search, see docstring
        logger.warning("LinkedIn discovery failed for %s: %s", key, exc)
        message = str(exc) if isinstance(exc, LinkedInError) else "La búsqueda en LinkedIn falló."
        _failures[key] = (time.time(), message)
    finally:
        _in_flight.pop(key, None)


async def search_linkedin_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
) -> dict[str, Any]:
    if not is_configured():
        raise LinkedInError("LinkedIn (Bright Data) is not configured (missing BRIGHTDATA_API_KEY).")

    keyword = " ".join((q or "").split()).lower()
    if not keyword:
        return {"results": [], "has_more": False}

    key: Key = (keyword, (location or settings.BRIGHTDATA_LINKEDIN_LOCATION).strip(), remote_type_filter or "")
    now = time.time()
    cached = _query_cache.get(key)
    fresh = cached is not None and now - cached["cached_at"] < _RESULTS_TTL_SECONDS

    if not fresh and key not in _in_flight:
        failure = _failures.get(key)
        if failure is not None and now - failure[0] < _FAILURE_TTL_SECONDS:
            if cached is None:
                raise LinkedInError(failure[1])
        elif await api_budget.try_consume_budget("linkedin"):
            _in_flight[key] = asyncio.create_task(_refresh(key))
        elif cached is None:
            raise LinkedInError(
                "Límite diario de búsquedas en LinkedIn alcanzado para cuidar el saldo — se reintenta mañana."
            )

    if cached is None:
        raise LinkedInPending(
            "Buscando en LinkedIn en segundo plano (tarda cerca de un minuto): vuelve a buscar en un momento."
        )

    results = [
        job
        for job in cached["results"]
        if not (remote_type_filter and job["remote_type"] and job["remote_type"] != remote_type_filter)
        and experience_level.matches(job["seniority"], experience_level_filter)
    ]
    return {"results": results, "has_more": False}


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _job_cache.get(job_id)
    if entry is None or time.time() - entry["cached_at"] > _RESULTS_TTL_SECONDS:
        _job_cache.pop(job_id, None)
        return None
    return entry["job"]
