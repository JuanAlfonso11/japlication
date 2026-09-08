"""Remote OK — free, no API key.

Previously investigated and set aside (see docs/PUBLIC_APIS_RESEARCH.md):
its Cloudflare layer refuses requests without a real browser User-Agent.
Re-verified live before integrating — it answers 200 with ~100 current
listings, and the project's shared USER_AGENT already *is* a browser
string, which is what the earlier note was worried about. The field names
are self-describing in the payload rather than guessed from third-party
scrapers, so the original reliability concern no longer holds.

**Their terms, and how this honours them.** The first element of the
response carries a `legal` notice asking that consumers link back to the
listing's page on Remote OK and name Remote OK as the source, on pain of
access being suspended. Both are satisfied:

  * `source_url` is deliberately the Remote OK page (`url`), never the
    employer's direct `apply_url`. The app's "Aplicar en el sitio original"
    button therefore sends the user *to Remote OK*, which is exactly the
    traffic the terms ask for.
  * The provider name is shown on every result card in Discover
    (PROVIDER_LABELS / SourceBadge), so the source is credited on screen.

The "follow, not nofollow" half of their notice is about SEO on a public
website and has no analogue in a private, single-operator app — there is no
public page here to place a link on.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.services import experience_level
from app.services.job_importer import USER_AGENT, html_to_text, parse_job_text_heuristic

ENDPOINT = "https://remoteok.com/api"
_CACHE_TTL_SECONDS = 15 * 60

_feed_cache: dict[str, Any] = {}
_search_cache: dict[str, dict[str, Any]] = {}


class RemoteOkError(RuntimeError):
    pass


def _normalize(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    job_id = raw.get("id")
    # Remote OK calls the job title "position"; "title" is absent.
    title = (raw.get("position") or "").strip()
    url = raw.get("url")
    if not job_id or not title or not url:
        return None

    company = (raw.get("company") or "").strip() or "Unknown company"
    description = html_to_text(raw.get("description") or "").strip() or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    tags = [str(t).strip() for t in (raw.get("tags") or []) if str(t).strip()]
    skills = list(parsed["skills_required"])
    seen = {s["name"].lower() for s in skills}
    for name in tags:
        if name.lower() not in seen:
            skills.append({"name": name, "importance": "required"})
            seen.add(name.lower())

    posted_at = None
    epoch = raw.get("epoch")
    if isinstance(epoch, (int, float)):
        try:
            posted_at = datetime.fromtimestamp(epoch, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            posted_at = None
    if posted_at is None and raw.get("date"):
        try:
            posted_at = datetime.fromisoformat(str(raw["date"]).replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    # Remote OK publishes annual USD figures. Zero means "not stated", not
    # "unpaid" — passing it through would render as a $0 salary band.
    def _salary(key: str) -> Optional[float]:
        value = raw.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
        return None

    salary_min = _salary("salary_min")
    salary_max = _salary("salary_max")

    return {
        "remoteok_job_id": str(job_id),
        "source": "remoteok",
        # Their page, not `apply_url` — see the module docstring: this is
        # the link-back their terms ask for.
        "source_url": url,
        "title": title,
        "company": company,
        "location": (raw.get("location") or "").strip() or "Remote",
        "remote_type": "remote",
        "employment_type": parsed["employment_type"],
        "seniority": experience_level.infer(title, description),
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": skills,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": "USD" if (salary_min or salary_max) else None,
        "posted_at": posted_at,
    }


async def _all_jobs() -> list[dict[str, Any]]:
    now = time.time()
    cached_jobs = _feed_cache.get("jobs")
    if cached_jobs is not None and now - _feed_cache.get("fetched_at", 0) < _CACHE_TTL_SECONDS:
        return cached_jobs

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # The browser User-Agent is load-bearing here, not cosmetic:
            # Cloudflare returns a challenge page to anything that looks
            # like a script, which is why this source was passed over the
            # first time round.
            resp = await client.get(
                ENDPOINT, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
    except httpx.HTTPError as exc:
        raise RemoteOkError("Could not reach Remote OK (network error).") from exc

    if resp.status_code != 200:
        raise RemoteOkError(f"Remote OK request failed with status {resp.status_code}.")

    try:
        payload = resp.json()
    except ValueError as exc:
        raise RemoteOkError("Remote OK returned a non-JSON response.") from exc

    if not isinstance(payload, list):
        raise RemoteOkError("Remote OK returned an unexpected payload shape.")

    # The first element is a legal/metadata notice, not a job — it has no
    # `id`, so _normalize drops it anyway, but skipping it explicitly makes
    # the intent obvious to the next reader.
    entries = [raw for raw in payload if isinstance(raw, dict) and raw.get("id")]

    jobs = [j for j in (_normalize(raw) for raw in entries) if j]
    _feed_cache["jobs"] = jobs
    _feed_cache["fetched_at"] = now
    return jobs


async def search_remoteok_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
) -> dict[str, Any]:
    jobs = await _all_jobs()

    now = time.time()
    results = []
    for job in jobs:
        if q:
            haystack = (
                f"{job['title']} {job['company']} {job['description']} "
                f"{' '.join(s['name'] for s in job['skills_required'])}"
            ).lower()
            if q.lower() not in haystack:
                continue
        loc = (location or "").strip().lower()
        if loc and loc not in ("worldwide", "remote", "remoto"):
            if not job["location"] or loc not in job["location"].lower():
                continue
        if remote_type_filter and remote_type_filter != "remote":
            continue
        if not experience_level.matches(job["seniority"], experience_level_filter):
            continue
        _search_cache[job["remoteok_job_id"]] = {"cached_at": now, "job": job}
        results.append(job)
    _cleanup_cache(now)

    return {"results": results, "has_more": False}


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
