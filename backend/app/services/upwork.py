"""Upwork integration: OAuth2 (authorization-code flow) + the GraphQL
`marketplaceJobPostings` query (https://api.upwork.com/graphql).

Unlike Google Jobs/SerpApi (one shared server-side API key) or Himalayas (no
key at all), Upwork requires each user to individually authorize the app
against *their own* Upwork account — there is no way to search on a user's
behalf without it. The flow:

1. `GET /integrations/upwork/authorize` -> `get_authorization_url()` sends
   the browser to Upwork's consent screen.
2. Upwork redirects back to `GET /integrations/upwork/callback?code&state`.
   `exchange_code_for_token()` swaps the code for an access/refresh token
   pair, which the router persists in `oauth_connections`.
3. `search_upwork_jobs()` runs the GraphQL query with that access token,
   transparently refreshing it first via `refresh_access_token()` if it's
   expired (or retrying once on a 401 if we don't have a tracked expiry).

Endpoints, per Upwork's OAuth2 documentation:
  authorize: https://www.upwork.com/ab/account-security/oauth2/authorize
  token:     https://www.upwork.com/api/v3/oauth2/token
  graphql:   https://api.upwork.com/graphql

The exact `marketplaceJobPostings` field/argument names below follow
Upwork's public GraphQL schema as documented at the time of writing. Upwork's
schema is only fully browsable via GraphQL introspection from an approved
developer account, so if Upwork returns a "Cannot query field ..." GraphQL
error, adjust `_SEARCH_QUERY` / `_build_filter()` to match your account's
live schema — everything else in this module (OAuth flow, token storage,
caching, normalization into a `Job`) is unaffected by that.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.services.job_importer import parse_job_text_heuristic

AUTHORIZATION_ENDPOINT = "https://www.upwork.com/ab/account-security/oauth2/authorize"
TOKEN_ENDPOINT = "https://www.upwork.com/api/v3/oauth2/token"
GRAPHQL_ENDPOINT = "https://api.upwork.com/graphql"

_CACHE_TTL_SECONDS = 15 * 60
# ciphertext/id -> {"cached_at": float, "job": {...normalized...}}
_search_cache: dict[str, dict[str, Any]] = {}


class UpworkError(RuntimeError):
    """Raised for any condition that should surface as a clean HTTP error."""


class UpworkNotConfigured(UpworkError):
    """UPWORK_CLIENT_ID/SECRET are not set — the integration is hidden."""


def is_configured() -> bool:
    return bool(settings.UPWORK_CLIENT_ID and settings.UPWORK_CLIENT_SECRET)


def _require_configured() -> None:
    if not is_configured():
        raise UpworkNotConfigured(
            "UPWORK_CLIENT_ID / UPWORK_CLIENT_SECRET are not configured. Register an app at "
            "https://www.upwork.com/developer/apps and set them in the backend's .env to enable "
            "the Upwork search provider."
        )


def get_authorization_url(state: str) -> str:
    _require_configured()
    params = {
        "response_type": "code",
        "client_id": settings.UPWORK_CLIENT_ID,
        "redirect_uri": settings.UPWORK_REDIRECT_URI,
        "state": state,
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


async def _post_token_request(data: dict[str, str]) -> dict[str, Any]:
    _require_configured()
    payload = {
        "client_id": settings.UPWORK_CLIENT_ID,
        "client_secret": settings.UPWORK_CLIENT_SECRET,
        **data,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                TOKEN_ENDPOINT,
                data=payload,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise UpworkError("Could not reach Upwork's token endpoint (network error).") from exc

    if resp.status_code != 200:
        raise UpworkError(f"Upwork token request failed with status {resp.status_code}: {resp.text[:300]}")

    try:
        return resp.json()
    except ValueError as exc:
        raise UpworkError("Upwork's token endpoint returned a non-JSON response.") from exc


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    """Returns {"access_token", "refresh_token", "token_type", "expires_at" (datetime|None)}."""
    data = await _post_token_request(
        {"grant_type": "authorization_code", "code": code, "redirect_uri": settings.UPWORK_REDIRECT_URI}
    )
    return _extract_token_fields(data)


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    data = await _post_token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
    return _extract_token_fields(data)


def _extract_token_fields(data: dict[str, Any]) -> dict[str, Any]:
    access_token = data.get("access_token")
    if not access_token:
        raise UpworkError("Upwork's token response did not include an access_token.")
    expires_in = data.get("expires_in")
    expires_at = None
    if isinstance(expires_in, (int, float)):
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return {
        "access_token": access_token,
        "refresh_token": data.get("refresh_token"),
        "token_type": data.get("token_type") or "Bearer",
        "expires_at": expires_at,
    }


_SEARCH_QUERY = """
query SearchJobs($filter: MarketplaceJobFilter, $first: Int) {
  marketplaceJobPostings(marketPlaceJobFilter: $filter, first: $first) {
    edges {
      node {
        id
        ciphertext
        title
        description
        experienceLevel
        publishedDateTime
        duration
        engagement
        category
        subcategory
        skills {
          name
        }
        amount {
          rawValue
          currency
        }
        hourlyBudgetMin {
          rawValue
          currency
        }
        hourlyBudgetMax {
          rawValue
          currency
        }
        client {
          companyName
          location {
            country
          }
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""


def _build_filter(q: Optional[str], skills: Optional[list[str]]) -> dict[str, Any]:
    filter_: dict[str, Any] = {}
    if q:
        filter_["titleExpression_eq"] = q
    if skills:
        filter_["skillExpression_eq"] = " OR ".join(skills)
    return filter_


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    title = raw.get("title") or "Untitled project"
    client = raw.get("client") or {}
    company = client.get("companyName") or "Cliente de Upwork"
    description = (raw.get("description") or "").strip() or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    skills_from_api = [
        {"name": s.get("name"), "importance": "required"}
        for s in (raw.get("skills") or [])
        if s.get("name")
    ]
    known = {s["name"].lower() for s in skills_from_api}
    extra_skills = [s for s in parsed["skills_required"] if s["name"].lower() not in known]

    fixed_amount = raw.get("amount") or {}
    hourly_min = raw.get("hourlyBudgetMin") or {}
    hourly_max = raw.get("hourlyBudgetMax") or {}

    is_hourly = bool(hourly_min.get("rawValue") or hourly_max.get("rawValue"))
    salary_min = salary_max = salary_currency = None
    budget_note = ""
    if is_hourly:
        salary_min = float(hourly_min["rawValue"]) if hourly_min.get("rawValue") else None
        salary_max = float(hourly_max["rawValue"]) if hourly_max.get("rawValue") else salary_min
        salary_currency = hourly_min.get("currency") or hourly_max.get("currency")
        budget_note = "Proyecto por hora (tarifa/hora, no salario anual)."
    elif fixed_amount.get("rawValue"):
        salary_min = salary_max = float(fixed_amount["rawValue"])
        salary_currency = fixed_amount.get("currency")
        budget_note = "Proyecto de precio fijo (presupuesto total, no salario anual)."

    posted_at = None
    published = raw.get("publishedDateTime")
    if published:
        try:
            posted_at = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    external_id = raw.get("ciphertext") or raw.get("id")

    return {
        "upwork_job_id": external_id,
        "source": "upwork",
        "source_url": f"https://www.upwork.com/jobs/{external_id}" if external_id else None,
        "title": title,
        "company": company,
        "location": (client.get("location") or {}).get("country") or "Remoto (freelance)",
        "remote_type": "remote",
        "employment_type": "contract",
        "seniority": (raw.get("experienceLevel") or parsed["seniority"] or "").lower() or None,
        "description": (f"{budget_note}\n\n{description}" if budget_note else description),
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": skills_from_api + extra_skills,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": salary_currency,
        "posted_at": posted_at,
        "is_hourly": is_hourly,
        "category": raw.get("category"),
    }


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def _graphql_request(access_token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                GRAPHQL_ENDPOINT,
                json={"query": query, "variables": variables},
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise UpworkError("Could not reach Upwork's GraphQL API (network error).") from exc

    if resp.status_code == 401:
        raise PermissionError("upwork access token expired or invalid")
    if resp.status_code != 200:
        raise UpworkError(f"Upwork GraphQL request failed with status {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise UpworkError("Upwork's GraphQL API returned a non-JSON response.") from exc

    if data.get("errors"):
        raise UpworkError("; ".join(e.get("message", "unknown error") for e in data["errors"]))
    return data.get("data") or {}


async def search_upwork_jobs(
    access_token: str,
    q: Optional[str] = None,
    skills: Optional[list[str]] = None,
    first: int = 20,
) -> dict[str, Any]:
    """Raises PermissionError if `access_token` is expired/invalid (the
    caller should refresh and retry once)."""
    variables = {"filter": _build_filter(q, skills), "first": first}
    data = await _graphql_request(access_token, _SEARCH_QUERY, variables)

    postings = (data.get("marketplaceJobPostings") or {})
    edges = postings.get("edges") or []

    now = time.time()
    results = []
    for edge in edges:
        node = edge.get("node") or {}
        normalized = _normalize(node)
        if normalized["upwork_job_id"]:
            _search_cache[normalized["upwork_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    page_info = postings.get("pageInfo") or {}
    return {"results": results, "has_more": bool(page_info.get("hasNextPage"))}


def get_cached_result(upwork_job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(upwork_job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(upwork_job_id, None)
        return None
    return entry["job"]
