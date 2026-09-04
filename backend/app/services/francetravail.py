"""France Travail (formerly Pôle Emploi) — official French employment
agency job-offers API. Free self-serve OAuth2 client credentials at
https://francetravail.io/. Docs:
https://francetravail.io/produits-partages/catalogue/offres-emploi

Authenticates via OAuth2 client_credentials against France Travail's own
identity provider (a separate host from the search API). The resulting
bearer token is cached in-process until shortly before it expires
(~25 min), so normal request volume needs at most one token refresh
every 25 minutes rather than one per search.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.services import experience_level
from app.services.job_importer import html_to_text, parse_job_text_heuristic

TOKEN_URL = "https://entreprise.francetravail.io/connexion/oauth2/access_token?realm=%2Fpartenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SCOPE = "api_offresdemploiv2 o2dsoffre"

_CACHE_TTL_SECONDS = 15 * 60
_search_cache: dict[str, dict[str, Any]] = {}
_token_cache: dict[str, Any] = {}

_EMPLOYMENT_TYPE_MAP = {"CDI": "full_time", "CDD": "contract", "MIS": "contract", "SAI": "contract", "LIB": "contract"}


class FranceTravailError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.FRANCE_TRAVAIL_CLIENT_ID and settings.FRANCE_TRAVAIL_CLIENT_SECRET)


async def _get_access_token() -> str:
    now = time.time()
    cached = _token_cache.get("token")
    if cached and _token_cache.get("expires_at", 0) > now:
        return cached

    data = {
        "grant_type": "client_credentials",
        "client_id": settings.FRANCE_TRAVAIL_CLIENT_ID,
        "client_secret": settings.FRANCE_TRAVAIL_CLIENT_SECRET,
        "scope": SCOPE,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
    except httpx.HTTPError as exc:
        raise FranceTravailError("Could not reach France Travail's auth server (network error).") from exc

    if resp.status_code != 200:
        raise FranceTravailError(f"France Travail auth failed with status {resp.status_code}.")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise FranceTravailError("France Travail auth returned a non-JSON response.") from exc

    token = payload.get("access_token")
    if not token:
        raise FranceTravailError("France Travail auth response had no access_token.")
    expires_in = payload.get("expires_in", 1500)
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + max(60, int(expires_in) - 60)
    return token


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    title = raw.get("intitule") or "Untitled position"
    company = (raw.get("entreprise") or {}).get("nom") or "Unknown company"
    description = html_to_text(raw.get("description") or "").strip() or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    employment_type = _EMPLOYMENT_TYPE_MAP.get(raw.get("typeContrat") or "", parsed["employment_type"])
    level = experience_level.infer(title, description) or parsed.get("seniority")

    location_name = (raw.get("lieuTravail") or {}).get("libelle")

    remote_type = parsed.get("remote_type")
    haystack = f"{title} {description}".lower()
    if remote_type is None and ("télétravail" in haystack or "teletravail" in haystack or "remote" in haystack):
        remote_type = "remote"

    salary_min = salary_max = salary_currency = None
    salaire_libelle = (raw.get("salaire") or {}).get("libelle")
    if salaire_libelle:
        nums = re.findall(r"[\d,.]+", salaire_libelle.replace(" ", ""))
        values: list[float] = []
        for n in nums:
            cleaned = n.replace(",", ".").rstrip(".")
            try:
                values.append(float(cleaned))
            except ValueError:
                continue
        if values:
            salary_min, salary_max = min(values), max(values)
            salary_currency = "EUR"

    posted_at = None
    date_creation = raw.get("dateCreation")
    if date_creation:
        try:
            posted_at = datetime.fromisoformat(str(date_creation).replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    return {
        "francetravail_job_id": raw.get("id"),
        "source": "francetravail",
        "source_url": (raw.get("origineOffre") or {}).get("urlOrigine"),
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
        "salary_currency": salary_currency,
        "posted_at": posted_at,
    }


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def search_francetravail_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
    page: int = 1,
    results_per_page: int = 25,
) -> dict[str, Any]:
    if not is_configured():
        raise FranceTravailError(
            "France Travail is not configured (missing FRANCE_TRAVAIL_CLIENT_ID/FRANCE_TRAVAIL_CLIENT_SECRET)."
        )

    token = await _get_access_token()

    params: dict[str, Any] = {}
    if q:
        params["motsCles"] = q
    if location:
        params["commune"] = location

    range_start = (page - 1) * results_per_page
    range_end = range_start + results_per_page - 1
    headers = {"Authorization": f"Bearer {token}", "Range": f"offres {range_start}-{range_end}"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(SEARCH_URL, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise FranceTravailError("Could not reach France Travail (network error).") from exc

    if resp.status_code not in (200, 206):
        raise FranceTravailError(f"France Travail request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise FranceTravailError("France Travail returned a non-JSON response.") from exc

    now = time.time()
    results = []
    for raw in data.get("resultats", []) or []:
        normalized = _normalize(raw)
        if remote_type_filter and normalized["remote_type"] and normalized["remote_type"] != remote_type_filter:
            continue
        if not experience_level.matches(normalized["seniority"], experience_level_filter):
            continue
        if normalized["francetravail_job_id"]:
            _search_cache[normalized["francetravail_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    content_range = resp.headers.get("Content-Range", "")
    has_more = False
    if "/" in content_range:
        try:
            total = int(content_range.rsplit("/", 1)[-1])
            has_more = range_end + 1 < total
        except ValueError:
            has_more = False

    return {"results": results, "has_more": has_more}


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
