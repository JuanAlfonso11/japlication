"""One place that knows the 15 job providers.

The same provider -> function mapping used to exist THREE times inside
api/v1/routers/jobs.py: an `if/elif` chain in the single-provider endpoint,
another one in the aggregate fan-out, and a dict of cache lookups. Plus a
hand-written regex listing all 15 names in a `Query(pattern=...)`, and a set
of "no-auth" names. Adding a provider meant five coordinated edits, and
missing one failed silently — search would work while "Add to queue" raised
KeyError -> 500.

They had already diverged: the single-provider endpoint forwarded `page`,
`sort`, `country`, `worldwide`, `seniority` and `employment_type`; the
aggregate forwarded none of them, so Discover and the automatic sweep were
quietly searching with fewer filters than a per-source search, and nothing
said so.

Each connector keeps its own module, its own error class and its own result
shape — this only centralizes the routing. `search` is a small adapter per
provider: it maps the uniform SearchParams onto whatever keyword arguments
that connector actually takes.

`external_id`: every connector returns its id under its own key
(`remotive_job_id`, `wwr_job_id`, `hn_job_id`, ...). `id_key` records that
name so the router can normalize without knowing any of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from app.services import (
    adzuna,
    arbeitnow,
    experience_level,
    getonbrd,
    hackernews,
    himalayas,
    jobicy,
    linkedin_jobs,
    remotejobs_org,
    remoteok,
    remotive,
    serpapi_jobs,
    themuse,
    usajobs,
    weworkremotely,
    workingnomads,
)


@dataclass(frozen=True)
class SearchParams:
    """What every provider search is given, before per-provider adaptation.

    `page` is the one field with two meanings, and the distinction matters:
    **None means "the caller is not paginating"** — the aggregate fan-out —
    and adapters then omit every pagination argument, so the connector keeps
    its own default. An int is a real 1-based page from the single-provider
    endpoint. Collapsing the two (defaulting to 1) would have silently
    changed what the aggregate sends.
    """

    q: Optional[str] = None
    location: Optional[str] = None
    experience_level_filter: Optional[str] = None
    remote_type_filter: Optional[str] = None
    category: Optional[str] = None
    page: Optional[int] = None
    # Only the single-provider endpoint exposes these.
    country: Optional[str] = None
    worldwide: Optional[bool] = None
    seniority: Optional[str] = None
    employment_type: Optional[str] = None
    sort: Optional[str] = None

    @property
    def paginating(self) -> bool:
        return self.page is not None

    @property
    def page_or_1(self) -> int:
        return self.page or 1


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    #: Key the connector puts its own id under, e.g. "wwr_job_id".
    id_key: str
    error_cls: type[Exception]
    #: (job_id) -> normalized result dict, or None if it aged out.
    get_cached: Callable[[str], Optional[dict[str, Any]]]
    #: (SearchParams) -> {"results": [...], "has_more": bool}
    search: Callable[[SearchParams], Awaitable[dict[str, Any]]]
    #: False for the three that need their own API key (adzuna, usajobs,
    #: serpapi). Used to be a separately maintained set of names.
    no_auth: bool = True


# ---------------------------------------------------------------- helpers
# Moved here from the router: they exist only to translate Discover's
# human-readable location into what one specific provider wants, so they
# belong beside the adapters that use them.

# Best-effort mapping from the human-readable location names Discover's
# dropdown sends to the geo slugs Himalayas' `country` and Jobicy's `geo`
# params expect. Providers that don't recognize a slug just don't filter by
# it rather than erroring, so an unmapped location still degrades gracefully
# to the substring match the other providers use.
LOCATION_SLUGS = {
    "united states": "usa",
    "canada": "canada",
    "united kingdom": "uk",
    "europe": "europe",
    "latin america": "latin-america",
    "mexico": "mexico",
    "brazil": "brazil",
    "argentina": "argentina",
    "colombia": "colombia",
    "chile": "chile",
    "dominican republic": "dominican-republic",
    "spain": "spain",
    "germany": "germany",
    "france": "france",
    "india": "india",
}


def location_slug(location: Optional[str]) -> Optional[str]:
    if not location:
        return None
    return LOCATION_SLUGS.get(location.strip().lower(), location.strip().lower())


def himalayas_worldwide(location: Optional[str], remote_type_filter: Optional[str]) -> bool:
    """Himalayas is a 100%-remote job board, so `worldwide` (roles open to
    candidates anywhere) is what we want whenever the user isn't narrowing to
    a specific country and isn't asking for onsite/hybrid (which Himalayas
    simply doesn't have)."""
    return not location and remote_type_filter in (None, "remote")


def themuse_location(location: Optional[str], remote_type_filter: Optional[str]) -> Optional[str]:
    """The Muse has no separate remote/onsite field — "Remote" is itself a
    location value there — so when the user wants remote work and hasn't
    picked a specific place, ask The Muse for "Remote" directly instead of
    leaving location unset (which would return everywhere, onsite included)."""
    if location:
        return location
    if remote_type_filter in (None, "remote"):
        return "Remote"
    return None


def _common(p: SearchParams) -> dict[str, Any]:
    """The four arguments every connector accepts."""
    return {
        "q": p.q,
        "location": p.location,
        "experience_level_filter": p.experience_level_filter,
        "remote_type_filter": p.remote_type_filter,
    }


# --------------------------------------------------------------- adapters
# One per provider. Each maps SearchParams onto that connector's own keyword
# arguments — which is the only reason a uniform registry needs any code at
# all. Pagination arguments are added ONLY when the caller is paginating
# (see SearchParams.page), so the aggregate fan-out keeps sending exactly
# what it sent before this refactor.


async def _search_himalayas(p: SearchParams) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "q": p.q,
        "country": p.country or location_slug(p.location),
        "worldwide": p.worldwide
        if p.worldwide is not None
        else himalayas_worldwide(p.location, p.remote_type_filter),
        "seniority": p.seniority
        or (
            experience_level.to_himalayas(p.experience_level_filter)
            if p.experience_level_filter
            else None
        ),
        "remote_type_filter": p.remote_type_filter,
    }
    if p.paginating:
        kwargs["employment_type"] = p.employment_type
        kwargs["sort"] = p.sort
        kwargs["page"] = p.page_or_1
    return await himalayas.search_himalayas_jobs(**kwargs)


async def _search_arbeitnow(p: SearchParams) -> dict[str, Any]:
    kwargs = _common(p)
    if p.paginating:
        kwargs["page"] = p.page_or_1
    return await arbeitnow.search_arbeitnow_jobs(**kwargs)


async def _search_remotive(p: SearchParams) -> dict[str, Any]:
    return await remotive.search_remotive_jobs(**_common(p), category=p.category)


async def _search_jobicy(p: SearchParams) -> dict[str, Any]:
    kwargs = _common(p)
    kwargs["location"] = location_slug(p.location)
    return await jobicy.search_jobicy_jobs(**kwargs, industry=p.category)


async def _search_remotejobs_org(p: SearchParams) -> dict[str, Any]:
    kwargs = _common(p)
    kwargs["category"] = p.category
    if p.paginating:
        kwargs["offset"] = (p.page_or_1 - 1) * 50
    return await remotejobs_org.search_remotejobs_org_jobs(**kwargs)


async def _search_themuse(p: SearchParams) -> dict[str, Any]:
    kwargs = _common(p)
    kwargs["location"] = themuse_location(p.location, p.remote_type_filter)
    kwargs["category"] = p.category
    if p.paginating:
        # The Muse pages from 0.
        kwargs["page"] = p.page_or_1 - 1
    return await themuse.search_themuse_jobs(**kwargs)


async def _search_weworkremotely(p: SearchParams) -> dict[str, Any]:
    return await weworkremotely.search_weworkremotely_jobs(**_common(p))


async def _search_workingnomads(p: SearchParams) -> dict[str, Any]:
    return await workingnomads.search_workingnomads_jobs(**_common(p))


async def _search_remoteok(p: SearchParams) -> dict[str, Any]:
    return await remoteok.search_remoteok_jobs(**_common(p))


async def _search_hackernews(p: SearchParams) -> dict[str, Any]:
    return await hackernews.search_hackernews_jobs(**_common(p))


async def _search_getonbrd(p: SearchParams) -> dict[str, Any]:
    kwargs = _common(p)
    if p.paginating:
        kwargs["page"] = p.page_or_1
    return await getonbrd.search_getonbrd_jobs(**kwargs)


async def _search_adzuna(p: SearchParams) -> dict[str, Any]:
    kwargs = _common(p)
    if p.paginating:
        kwargs["page"] = p.page_or_1
    return await adzuna.search_adzuna_jobs(**kwargs)


async def _search_usajobs(p: SearchParams) -> dict[str, Any]:
    kwargs = _common(p)
    if p.paginating:
        kwargs["page"] = p.page_or_1
    return await usajobs.search_usajobs_jobs(**kwargs)


async def _search_linkedin(p: SearchParams) -> dict[str, Any]:
    return await linkedin_jobs.search_linkedin_jobs(**_common(p))


async def _search_serpapi(p: SearchParams) -> dict[str, Any]:
    return await serpapi_jobs.search_serpapi_jobs(**_common(p))


# --------------------------------------------------------------- registry
# The single source of truth. Adding a provider is now one entry here plus
# the connector module itself — no router edits, no regex to update, no
# cache dict to remember.

_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec("himalayas", "himalayas_job_id", himalayas.HimalayasError,
                 himalayas.get_cached_result, _search_himalayas),
    ProviderSpec("arbeitnow", "arbeitnow_job_id", arbeitnow.ArbeitnowError,
                 arbeitnow.get_cached_result, _search_arbeitnow),
    ProviderSpec("remotive", "remotive_job_id", remotive.RemotiveError,
                 remotive.get_cached_result, _search_remotive),
    ProviderSpec("jobicy", "jobicy_job_id", jobicy.JobicyError,
                 jobicy.get_cached_result, _search_jobicy),
    ProviderSpec("remotejobs_org", "remotejobs_org_job_id", remotejobs_org.RemoteJobsOrgError,
                 remotejobs_org.get_cached_result, _search_remotejobs_org),
    ProviderSpec("themuse", "themuse_job_id", themuse.TheMuseError,
                 themuse.get_cached_result, _search_themuse),
    ProviderSpec("weworkremotely", "wwr_job_id", weworkremotely.WeWorkRemotelyError,
                 weworkremotely.get_cached_result, _search_weworkremotely),
    ProviderSpec("hackernews", "hn_job_id", hackernews.HackerNewsError,
                 hackernews.get_cached_result, _search_hackernews),
    ProviderSpec("getonbrd", "getonbrd_job_id", getonbrd.GetOnBrdError,
                 getonbrd.get_cached_result, _search_getonbrd),
    ProviderSpec("workingnomads", "workingnomads_job_id", workingnomads.WorkingNomadsError,
                 workingnomads.get_cached_result, _search_workingnomads),
    ProviderSpec("remoteok", "remoteok_job_id", remoteok.RemoteOkError,
                 remoteok.get_cached_result, _search_remoteok),
    ProviderSpec("linkedin", "linkedin_job_id", linkedin_jobs.LinkedInError,
                 linkedin_jobs.get_cached_result, _search_linkedin),
    # These three need their own API key (see .env); without one they raise
    # their own error and the aggregate reports them as unconfigured.
    ProviderSpec("adzuna", "adzuna_job_id", adzuna.AdzunaError,
                 adzuna.get_cached_result, _search_adzuna, no_auth=False),
    ProviderSpec("usajobs", "usajobs_job_id", usajobs.USAJobsError,
                 usajobs.get_cached_result, _search_usajobs, no_auth=False),
    ProviderSpec("serpapi", "serpapi_job_id", serpapi_jobs.SerpApiError,
                 serpapi_jobs.get_cached_result, _search_serpapi, no_auth=False),
)

PROVIDERS: dict[str, ProviderSpec] = {spec.name: spec for spec in _SPECS}
PROVIDER_NAMES: tuple[str, ...] = tuple(PROVIDERS)

#: For FastAPI's `Query(pattern=...)`. Derived, so the accepted values can
#: never drift from the implemented ones — it was a hand-typed regex listing
#: all 15 names.
PROVIDER_NAMES_PATTERN = "^(" + "|".join(PROVIDER_NAMES) + ")$"

#: Names that need no credentials. Was a separately maintained literal set.
NO_AUTH_PROVIDERS: frozenset[str] = frozenset(s.name for s in _SPECS if s.no_auth)


def get_provider(name: str) -> ProviderSpec:
    """Raises KeyError for an unknown name — which FastAPI's pattern on the
    query parameter already prevents, and which is a bug rather than user
    input anywhere else."""
    return PROVIDERS[name]


def normalize_results(spec: ProviderSpec, raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rewrites each result's provider-specific id key to `external_id`.

    Entries missing an id are dropped: they cannot be imported later, and a
    result you cannot act on is worse than one that is not shown.
    """
    out: list[dict[str, Any]] = []
    for r in raw_results:
        job_id = r.get(spec.id_key)
        if not job_id:
            continue
        rest = {k: v for k, v in r.items() if k != spec.id_key}
        out.append({"external_id": job_id, **rest})
    return out
