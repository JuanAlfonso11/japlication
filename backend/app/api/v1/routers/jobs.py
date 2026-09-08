import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.application import Application
from app.models.career_profile import CareerProfile
from app.models.device_token import DeviceToken
from app.models.enums import ApplicationStatus, JobSource
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.user import User
from app.schemas.job import Job as JobSchema
from app.schemas.job import (
    AggregateSearchResponse,
    AggregateSourceStatus,
    AutoImportResponse,
    ExternalJobImportRequest,
    ExternalJobResult,
    ExternalJobsSearchResponse,
    JobCreate,
    JobImportRequest,
    JobListResponse,
)
from app.schemas.job_match import MatchResult
from app.services import (
    adzuna,
    api_budget,
    arbeitnow,
    experience_level,
    getonbrd,
    hackernews,
    himalayas,
    jobicy,
    push_notifications,
    remotejobs_org,
    remotive,
    serpapi_jobs,
    themuse,
    usajobs,
    weworkremotely,
    workingnomads,
    remoteok,
)
from app.services.job_dedupe import dedupe_external_results
from app.services.job_importer import import_job_from_url
from app.services.match_engine import compute_and_persist_match

router = APIRouter(tags=["jobs"])

# Every JobSource enum value that comes from a live search provider (as
# opposed to url_import/manual) — see docs/PUBLIC_APIS_RESEARCH.md for what
# was investigated and why Google Jobs/Upwork/LinkedIn/Indeed aren't (and,
# for LinkedIn/Indeed, can't be) part of this list.
_NO_AUTH_PROVIDERS = {
    "himalayas", "arbeitnow", "remotive", "jobicy", "remotejobs_org", "themuse",
    "weworkremotely", "hackernews", "getonbrd", "workingnomads", "remoteok",
}

# Registration-required providers. Each degrades gracefully when its keys
# aren't set in .env: its search_*_jobs() raises a clear *Error, which the
# single-provider endpoint turns into a 502 and the aggregate fan-out turns
# into a per-source error message — never a hard failure for the others.
_KEYED_PROVIDERS = {"adzuna", "usajobs", "serpapi"}

_SEARCH_PROVIDERS = _NO_AUTH_PROVIDERS | _KEYED_PROVIDERS

# Adzuna and SerpApi both have a monthly call quota (1,000/month and
# 250/month respectively — docs/PUBLIC_APIS_RESEARCH.md #9 and #12); an
# unattended 2-hour sweep alone would be 12 calls/day (~360/month) to each,
# already over SerpApi's quota before counting a single manual Discover
# search. app.services.api_budget caps every quota-limited provider at
# DAILY_CALL_BUDGET (8) calls/day — 240/month, safely under both quotas —
# enforced once, inside _run_search_provider below, so it applies
# uniformly everywhere a provider gets called: the scheduled sweep, pull-
# to-refresh, and Discover's explicit search all share the same daily
# budget rather than each needing their own carve-out.

# Best-effort mapping from the human-readable location names Discover's
# dropdown sends to the geo slugs Himalayas' `country` and Jobicy's `geo`
# params expect. Providers that don't recognize a slug just don't filter by
# it rather than erroring, so an unmapped location still degrades gracefully
# to the substring match the other four providers use.
_LOCATION_SLUGS = {
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
    "asia pacific": "apac",
    "australia": "australia",
}


def _location_slug(location: Optional[str]) -> Optional[str]:
    if not location:
        return None
    return _LOCATION_SLUGS.get(location.strip().lower(), location.strip().lower())


def _himalayas_worldwide(location: Optional[str], remote_type_filter: Optional[str]) -> bool:
    """Himalayas is a 100%-remote job board, so `worldwide` (roles open to
    candidates anywhere) is what we want whenever the user isn't narrowing
    to a specific country and isn't asking for onsite/hybrid (which
    Himalayas simply doesn't have — see remote_type_filter's own
    post-filter for how that case naturally yields zero results)."""
    return not location and remote_type_filter in (None, "remote")


def _themuse_location(location: Optional[str], remote_type_filter: Optional[str]) -> Optional[str]:
    """The Muse has no separate remote/onsite field — "Remote" is itself a
    location value there — so when the user wants remote work and hasn't
    picked a specific place, ask The Muse for "Remote" directly instead of
    leaving location unset (which would return everywhere, onsite included)."""
    if location:
        return location
    if remote_type_filter in (None, "remote"):
        return "Remote"
    return None


async def _ensure_match(job: Job, user_id: UUID, db: AsyncSession) -> None:
    """Computes and persists a JobMatch for a freshly-added job, if the
    user has a saved career profile to score it against. Without this,
    GET /matches (an INNER JOIN against job_matches) would silently never
    surface a job added via URL import, manual creation, or "add to
    queue" from Discover — nothing else computes a match for it, unlike
    the automatic sweep (run_auto_import_for_user), which always has.
    A no-op (not an error) if there's no profile yet — same
    graceful-degradation as everywhere else a career profile is optional."""
    existing = await db.execute(
        select(JobMatch.id).where(JobMatch.user_id == user_id, JobMatch.job_id == job.id)
    )
    if existing.scalar_one_or_none() is not None:
        return
    profile = (
        await db.execute(select(CareerProfile).where(CareerProfile.user_id == user_id))
    ).scalar_one_or_none()
    if profile is None:
        return
    await compute_and_persist_match(profile, job, user_id, db)


async def _attach_match(job: Job, user_id: UUID, db: AsyncSession) -> JobSchema:
    schema = JobSchema.model_validate(job)
    result = await db.execute(
        select(JobMatch).where(JobMatch.user_id == user_id, JobMatch.job_id == job.id)
    )
    match = result.scalar_one_or_none()
    if match is not None:
        schema.match = MatchResult.model_validate(match)
    return schema


@router.post("/jobs/import", response_model=JobSchema, status_code=status.HTTP_201_CREATED)
async def import_job(
    payload: JobImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobSchema:
    existing = await db.execute(select(Job).where(Job.source_url == payload.url))
    existing_job = existing.scalar_one_or_none()
    if existing_job is not None:
        await _ensure_match(existing_job, current_user.id, db)
        return await _attach_match(existing_job, current_user.id, db)

    parsed = await import_job_from_url(payload.url)

    job = Job(
        imported_by=current_user.id,
        source=JobSource.url_import,
        source_url=parsed.get("source_url"),
        title=parsed["title"],
        company=parsed["company"],
        location=parsed.get("location"),
        remote_type=parsed.get("remote_type"),
        employment_type=parsed.get("employment_type"),
        seniority=parsed.get("seniority"),
        description=parsed["description"],
        requirements=parsed.get("requirements") or [],
        responsibilities=parsed.get("responsibilities") or [],
        skills_required=parsed.get("skills_required") or [],
        salary_min=parsed.get("salary_min"),
        salary_max=parsed.get("salary_max"),
        salary_currency=parsed.get("salary_currency"),
        posted_at=parsed.get("posted_at"),
        raw_html=parsed.get("raw_html"),
    )
    db.add(job)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        # Race: another request imported the same URL concurrently.
        existing = await db.execute(select(Job).where(Job.source_url == payload.url))
        existing_job = existing.scalar_one_or_none()
        if existing_job is not None:
            await _ensure_match(existing_job, current_user.id, db)
            return await _attach_match(existing_job, current_user.id, db)
        raise HTTPException(status_code=422, detail="could not parse job posting")
    await db.refresh(job)
    await _ensure_match(job, current_user.id, db)
    return await _attach_match(job, current_user.id, db)


@router.post("/jobs", response_model=JobSchema, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobSchema:
    if payload.source_url:
        existing = await db.execute(select(Job).where(Job.source_url == payload.source_url))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="A job with this source_url already exists.")

    job = Job(
        imported_by=current_user.id,
        source=JobSource.manual,
        source_url=payload.source_url,
        title=payload.title,
        company=payload.company,
        location=payload.location,
        remote_type=payload.remote_type,
        employment_type=payload.employment_type,
        seniority=payload.seniority,
        description=payload.description,
        requirements=payload.requirements,
        responsibilities=payload.responsibilities,
        skills_required=[s.model_dump() for s in payload.skills_required],
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        salary_currency=payload.salary_currency,
        posted_at=payload.posted_at,
        requires_cover_letter=payload.requires_cover_letter,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await _ensure_match(job, current_user.id, db)
    return await _attach_match(job, current_user.id, db)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    query: Optional[str] = Query(None),
    status_filter: Optional[ApplicationStatus] = Query(None, alias="status"),
    min_score: Optional[float] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobListResponse:
    base = select(Job)
    count_base = select(func.count(Job.id.distinct()))

    if status_filter is not None:
        base = base.join(Application, (Application.job_id == Job.id) & (Application.user_id == current_user.id))
        base = base.where(Application.status == status_filter)
        count_base = count_base.join(
            Application, (Application.job_id == Job.id) & (Application.user_id == current_user.id)
        ).where(Application.status == status_filter)

    if min_score is not None:
        base = base.join(JobMatch, (JobMatch.job_id == Job.id) & (JobMatch.user_id == current_user.id))
        base = base.where(JobMatch.overall_score >= min_score)
        count_base = count_base.join(
            JobMatch, (JobMatch.job_id == Job.id) & (JobMatch.user_id == current_user.id)
        ).where(JobMatch.overall_score >= min_score)

    if query:
        like = f"%{query}%"
        base = base.where((Job.title.ilike(like)) | (Job.company.ilike(like)) | (Job.description.ilike(like)))
        count_base = count_base.where(
            (Job.title.ilike(like)) | (Job.company.ilike(like)) | (Job.description.ilike(like))
        )

    total = (await db.execute(count_base)).scalar_one()

    base = base.order_by(Job.created_at.desc()).limit(limit).offset(offset)
    jobs = (await db.execute(base)).scalars().all()

    matches_by_job_id: dict[UUID, JobMatch] = {}
    if jobs:
        match_rows = (
            await db.execute(
                select(JobMatch).where(
                    JobMatch.user_id == current_user.id,
                    JobMatch.job_id.in_([job.id for job in jobs]),
                )
            )
        ).scalars().all()
        matches_by_job_id = {m.job_id: m for m in match_rows}

    items = []
    for job in jobs:
        schema = JobSchema.model_validate(job)
        match = matches_by_job_id.get(job.id)
        if match is not None:
            schema.match = MatchResult.model_validate(match)
        items.append(schema)
    return JobListResponse(items=items, total=total)


@router.get("/jobs/search", response_model=ExternalJobsSearchResponse)
async def search_jobs(
    provider: str = Query(
        "himalayas",
        pattern="^(himalayas|arbeitnow|remotive|jobicy|remotejobs_org|themuse|weworkremotely|hackernews|getonbrd|workingnomads|remoteok|adzuna|usajobs|serpapi)$",
    ),
    q: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    experience_level_filter: Optional[str] = Query(
        None, alias="experience_level", pattern="^(internship|entry|mid|senior|lead)$"
    ),
    remote_type_filter: Optional[str] = Query(None, alias="remote_type", pattern="^(remote|hybrid|onsite)$"),
    country: Optional[str] = Query(None),
    worldwide: Optional[bool] = Query(None),
    seniority: Optional[str] = Query(None),
    employment_type: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    current_user: User = Depends(get_current_user),
) -> ExternalJobsSearchResponse:
    """Live-search one provider. Nothing is persisted — pick a
    result and call POST /jobs/search/import to add it to `jobs`.

    See GET /jobs/search/aggregate to query all twelve providers in one
    call, which is what Discover uses by default. adzuna/usajobs/serpapi
    require their own API keys (see .env) — calling them without keys
    configured returns a 502.
    """
    if provider == "himalayas":
        try:
            data = await himalayas.search_himalayas_jobs(
                q=q,
                country=country or _location_slug(location),
                worldwide=worldwide if worldwide is not None else _himalayas_worldwide(location, remote_type_filter),
                seniority=seniority or (experience_level.to_himalayas(experience_level_filter) if experience_level_filter else None),
                employment_type=employment_type,
                sort=sort,
                remote_type_filter=remote_type_filter,
                page=page,
            )
        except himalayas.HimalayasError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        results = [
            ExternalJobResult(external_id=r["himalayas_job_id"], **{k: v for k, v in r.items() if k != "himalayas_job_id"})
            for r in data["results"]
            if r.get("himalayas_job_id")
        ]
        return ExternalJobsSearchResponse(
            provider="himalayas", results=results, page=page + 1 if data["has_more"] else None, has_more=data["has_more"]
        )

    if provider == "arbeitnow":
        try:
            data = await arbeitnow.search_arbeitnow_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter, page=page,
            )
        except arbeitnow.ArbeitnowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        results = [
            ExternalJobResult(external_id=r["arbeitnow_job_id"], **{k: v for k, v in r.items() if k != "arbeitnow_job_id"})
            for r in data["results"]
            if r.get("arbeitnow_job_id")
        ]
        return ExternalJobsSearchResponse(
            provider="arbeitnow", results=results, page=page + 1 if data["has_more"] else None, has_more=data["has_more"]
        )

    if provider == "remotive":
        try:
            data = await remotive.search_remotive_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter, category=category,
            )
        except remotive.RemotiveError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        results = [
            ExternalJobResult(external_id=r["remotive_job_id"], **{k: v for k, v in r.items() if k != "remotive_job_id"})
            for r in data["results"]
            if r.get("remotive_job_id")
        ]
        return ExternalJobsSearchResponse(provider="remotive", results=results, has_more=False)

    if provider == "jobicy":
        try:
            data = await jobicy.search_jobicy_jobs(
                q=q, location=_location_slug(location), experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter, industry=category,
            )
        except jobicy.JobicyError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        results = [
            ExternalJobResult(external_id=r["jobicy_job_id"], **{k: v for k, v in r.items() if k != "jobicy_job_id"})
            for r in data["results"]
            if r.get("jobicy_job_id")
        ]
        return ExternalJobsSearchResponse(provider="jobicy", results=results, has_more=False)

    if provider == "remotejobs_org":
        offset = (page - 1) * 50
        try:
            data = await remotejobs_org.search_remotejobs_org_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter, category=category, offset=offset,
            )
        except remotejobs_org.RemoteJobsOrgError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        results = [
            ExternalJobResult(
                external_id=r["remotejobs_org_job_id"],
                **{k: v for k, v in r.items() if k != "remotejobs_org_job_id"},
            )
            for r in data["results"]
            if r.get("remotejobs_org_job_id")
        ]
        return ExternalJobsSearchResponse(
            provider="remotejobs_org", results=results, page=page + 1 if data["has_more"] else None, has_more=data["has_more"]
        )

    if provider == "themuse":
        try:
            data = await themuse.search_themuse_jobs(
                q=q,
                location=_themuse_location(location, remote_type_filter),
                experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
                category=category,
                page=page - 1,
            )
        except themuse.TheMuseError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        results = [
            ExternalJobResult(external_id=r["themuse_job_id"], **{k: v for k, v in r.items() if k != "themuse_job_id"})
            for r in data["results"]
            if r.get("themuse_job_id")
        ]
        return ExternalJobsSearchResponse(
            provider="themuse", results=results, page=page + 1 if data["has_more"] else None, has_more=data["has_more"]
        )

    if provider == "weworkremotely":
        try:
            data = await weworkremotely.search_weworkremotely_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
            )
        except weworkremotely.WeWorkRemotelyError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        results = [
            ExternalJobResult(external_id=r["wwr_job_id"], **{k: v for k, v in r.items() if k != "wwr_job_id"})
            for r in data["results"]
            if r.get("wwr_job_id")
        ]
        return ExternalJobsSearchResponse(provider="weworkremotely", results=results, has_more=False)

    if provider == "workingnomads":
        try:
            data = await workingnomads.search_workingnomads_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
            )
        except workingnomads.WorkingNomadsError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        results = [
            ExternalJobResult(external_id=r["workingnomads_job_id"], **{k: v for k, v in r.items() if k != "workingnomads_job_id"})
            for r in data["results"]
            if r.get("workingnomads_job_id")
        ]
        return ExternalJobsSearchResponse(provider="workingnomads", results=results, has_more=False)

    if provider == "remoteok":
        try:
            data = await remoteok.search_remoteok_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
            )
        except remoteok.RemoteOkError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        results = [
            ExternalJobResult(external_id=r["remoteok_job_id"], **{k: v for k, v in r.items() if k != "remoteok_job_id"})
            for r in data["results"]
            if r.get("remoteok_job_id")
        ]
        return ExternalJobsSearchResponse(provider="remoteok", results=results, has_more=False)

    if provider == "hackernews":
        try:
            data = await hackernews.search_hackernews_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
            )
        except hackernews.HackerNewsError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        results = [
            ExternalJobResult(external_id=r["hn_job_id"], **{k: v for k, v in r.items() if k != "hn_job_id"})
            for r in data["results"]
            if r.get("hn_job_id")
        ]
        return ExternalJobsSearchResponse(provider="hackernews", results=results, has_more=False)

    if provider == "getonbrd":
        try:
            data = await getonbrd.search_getonbrd_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter, page=page,
            )
        except getonbrd.GetOnBrdError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        results = [
            ExternalJobResult(external_id=r["getonbrd_job_id"], **{k: v for k, v in r.items() if k != "getonbrd_job_id"})
            for r in data["results"]
            if r.get("getonbrd_job_id")
        ]
        return ExternalJobsSearchResponse(
            provider="getonbrd", results=results, page=page + 1 if data["has_more"] else None, has_more=data["has_more"]
        )

    if provider == "adzuna":
        try:
            data = await adzuna.search_adzuna_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter, page=page,
            )
        except adzuna.AdzunaError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        results = [
            ExternalJobResult(external_id=r["adzuna_job_id"], **{k: v for k, v in r.items() if k != "adzuna_job_id"})
            for r in data["results"]
            if r.get("adzuna_job_id")
        ]
        return ExternalJobsSearchResponse(
            provider="adzuna", results=results, page=page + 1 if data["has_more"] else None, has_more=data["has_more"]
        )

    if provider == "usajobs":
        try:
            data = await usajobs.search_usajobs_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter, page=page,
            )
        except usajobs.USAJobsError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        results = [
            ExternalJobResult(external_id=r["usajobs_job_id"], **{k: v for k, v in r.items() if k != "usajobs_job_id"})
            for r in data["results"]
            if r.get("usajobs_job_id")
        ]
        return ExternalJobsSearchResponse(
            provider="usajobs", results=results, page=page + 1 if data["has_more"] else None, has_more=data["has_more"]
        )

    # provider == "serpapi"
    try:
        data = await serpapi_jobs.search_serpapi_jobs(
            q=q, location=location, experience_level_filter=experience_level_filter,
            remote_type_filter=remote_type_filter,
        )
    except serpapi_jobs.SerpApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    results = [
        ExternalJobResult(external_id=r["serpapi_job_id"], **{k: v for k, v in r.items() if k != "serpapi_job_id"})
        for r in data["results"]
        if r.get("serpapi_job_id")
    ]
    return ExternalJobsSearchResponse(provider="serpapi", results=results, has_more=False)


async def _run_search_provider(
    provider: str,
    q: Optional[str],
    location: Optional[str],
    experience_level_filter: Optional[str],
    remote_type_filter: Optional[str],
    category: Optional[str],
) -> tuple[str, list[ExternalJobResult], Optional[str]]:
    """Runs one provider search and normalizes both its results and any
    failure into a uniform (provider, results, error) tuple, so one
    provider erroring — including a keyed provider whose credentials
    aren't configured — never breaks the others in the aggregate fan-out.

    For a quota-limited provider (see app.services.api_budget), this first
    checks/consumes today's call budget — once the daily cap is hit, it
    returns an empty result with an explanatory error instead of ever
    reaching the network, same shape as any other provider failure."""
    if not await api_budget.try_consume_budget(provider):
        return provider, [], "Límite diario de llamadas alcanzado para proteger la cuota mensual — se reintenta mañana."
    try:
        if provider == "himalayas":
            data = await himalayas.search_himalayas_jobs(
                q=q,
                country=_location_slug(location),
                worldwide=_himalayas_worldwide(location, remote_type_filter),
                seniority=experience_level.to_himalayas(experience_level_filter) if experience_level_filter else None,
                remote_type_filter=remote_type_filter,
            )
            id_key = "himalayas_job_id"
        elif provider == "arbeitnow":
            data = await arbeitnow.search_arbeitnow_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
            )
            id_key = "arbeitnow_job_id"
        elif provider == "remotive":
            data = await remotive.search_remotive_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter, category=category,
            )
            id_key = "remotive_job_id"
        elif provider == "jobicy":
            data = await jobicy.search_jobicy_jobs(
                q=q, location=_location_slug(location), experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter, industry=category,
            )
            id_key = "jobicy_job_id"
        elif provider == "remotejobs_org":
            data = await remotejobs_org.search_remotejobs_org_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter, category=category,
            )
            id_key = "remotejobs_org_job_id"
        elif provider == "themuse":
            data = await themuse.search_themuse_jobs(
                q=q, location=_themuse_location(location, remote_type_filter),
                experience_level_filter=experience_level_filter, remote_type_filter=remote_type_filter,
                category=category,
            )
            id_key = "themuse_job_id"
        elif provider == "weworkremotely":
            data = await weworkremotely.search_weworkremotely_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
            )
            id_key = "wwr_job_id"
        elif provider == "workingnomads":
            data = await workingnomads.search_workingnomads_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
            )
            id_key = "workingnomads_job_id"
        elif provider == "remoteok":
            data = await remoteok.search_remoteok_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
            )
            id_key = "remoteok_job_id"
        elif provider == "hackernews":
            data = await hackernews.search_hackernews_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
            )
            id_key = "hn_job_id"
        elif provider == "getonbrd":
            data = await getonbrd.search_getonbrd_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
            )
            id_key = "getonbrd_job_id"
        elif provider == "adzuna":
            data = await adzuna.search_adzuna_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
            )
            id_key = "adzuna_job_id"
        elif provider == "usajobs":
            data = await usajobs.search_usajobs_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
            )
            id_key = "usajobs_job_id"
        elif provider == "serpapi":
            data = await serpapi_jobs.search_serpapi_jobs(
                q=q, location=location, experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
            )
            id_key = "serpapi_job_id"
        else:
            return provider, [], f"Unknown provider '{provider}'."
    except Exception as exc:  # noqa: BLE001 — any provider failure is reported, never raised
        return provider, [], str(exc)

    results = [
        ExternalJobResult(external_id=r[id_key], **{k: v for k, v in r.items() if k != id_key})
        for r in data["results"]
        if r.get(id_key)
    ]
    return provider, results, None


def _aggregate_sort_key(result: ExternalJobResult) -> datetime:
    posted_at = result.posted_at
    if posted_at is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if posted_at.tzinfo is None:
        return posted_at.replace(tzinfo=timezone.utc)
    return posted_at


@router.get("/jobs/search/aggregate", response_model=AggregateSearchResponse)
@limiter.limit("10/minute")
async def search_jobs_aggregate(
    request: Request,
    q: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    experience_level_filter: Optional[str] = Query(
        None, alias="experience_level", pattern="^(internship|entry|mid|senior|lead)$"
    ),
    remote_type_filter: Optional[str] = Query(
        "remote", alias="remote_type", pattern="^(remote|hybrid|onsite)$"
    ),
    category: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
) -> AggregateSearchResponse:
    """Fans out to every job-search provider at once (Himalayas, Arbeitnow,
    Remotive, Jobicy, RemoteJobs.org, The Muse, We Work Remotely, Hacker
    News, Get on Board, plus Adzuna/USAJobs/SerpApi
    whenever their keys are set in .env) and merges the results into one
    list, newest first — this is what the Discover tab's "search all
    sources" action calls. A provider
    that errors — including a keyed provider with no credentials
    configured — doesn't take the others down with it: its failure shows
    up in `sources` instead of the result list. `location` is purely
    geographic (e.g. "Mexico"); `remote_type` (remote/hybrid/onsite) is
    independent and defaults to "remote" to preserve the historical
    default of showing only remote-friendly postings when no filters are
    set."""
    outcomes = await asyncio.gather(
        *[
            _run_search_provider(p, q, location, experience_level_filter, remote_type_filter, category)
            for p in _SEARCH_PROVIDERS
        ]
    )

    all_results: list[ExternalJobResult] = []
    sources: list[AggregateSourceStatus] = []
    for provider, results, error in outcomes:
        all_results.extend(results)
        sources.append(AggregateSourceStatus(provider=provider, count=len(results), error=error))

    all_results.sort(key=_aggregate_sort_key, reverse=True)
    # Sort first, dedupe second: the providers overlap heavily (one vacancy
    # commonly appears on three or four of them), and deduping the sorted
    # list means the copy that survives is the newest one. Per-provider
    # `sources` counts stay pre-dedupe on purpose — they report what each
    # provider returned, which is what makes them useful for spotting a
    # provider that quietly went empty.
    all_results = dedupe_external_results(all_results)
    return AggregateSearchResponse(results=all_results, sources=sources)


async def _get_or_create_external_job(
    cached: dict, source: str, user_id: UUID, db: AsyncSession
) -> tuple[Job, bool]:
    """Creates a `jobs` row from a normalized external search result, or
    returns the existing one if this source_url was already imported by
    anyone. Returns (job, created) — shared by the manual "Add to queue"
    import and the CV-upload auto-import."""
    if cached.get("source_url"):
        existing = await db.execute(select(Job).where(Job.source_url == cached["source_url"]))
        existing_job = existing.scalar_one_or_none()
        if existing_job is not None:
            return existing_job, False

    job = Job(
        imported_by=user_id,
        source=JobSource(source),
        source_url=cached.get("source_url"),
        title=cached["title"],
        company=cached["company"],
        location=cached.get("location"),
        remote_type=cached.get("remote_type"),
        employment_type=cached.get("employment_type"),
        seniority=cached.get("seniority"),
        description=cached["description"],
        requirements=cached.get("requirements") or [],
        responsibilities=cached.get("responsibilities") or [],
        skills_required=cached.get("skills_required") or [],
        salary_min=cached.get("salary_min"),
        salary_max=cached.get("salary_max"),
        salary_currency=cached.get("salary_currency"),
        posted_at=cached.get("posted_at"),
    )
    db.add(job)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        if cached.get("source_url"):
            existing = await db.execute(select(Job).where(Job.source_url == cached["source_url"]))
            existing_job = existing.scalar_one_or_none()
            if existing_job is not None:
                return existing_job, False
        raise
    await db.refresh(job)
    return job, True


@router.post("/jobs/search/import", response_model=JobSchema, status_code=status.HTTP_201_CREATED)
async def import_external_job(
    payload: ExternalJobImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobSchema:
    """Persist an external search result (found via GET /jobs/search) as a
    `jobs` row. Reads the normalized result from that provider's short-lived
    search cache rather than re-querying it."""
    if payload.source not in _SEARCH_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Unknown source '{payload.source}'.")

    cache_lookup = {
        "himalayas": himalayas.get_cached_result,
        "arbeitnow": arbeitnow.get_cached_result,
        "remotive": remotive.get_cached_result,
        "jobicy": jobicy.get_cached_result,
        "remotejobs_org": remotejobs_org.get_cached_result,
        "themuse": themuse.get_cached_result,
        "weworkremotely": weworkremotely.get_cached_result,
        "hackernews": hackernews.get_cached_result,
        "getonbrd": getonbrd.get_cached_result,
        "workingnomads": workingnomads.get_cached_result,
        "remoteok": remoteok.get_cached_result,
        "adzuna": adzuna.get_cached_result,
        "usajobs": usajobs.get_cached_result,
        "serpapi": serpapi_jobs.get_cached_result,
    }[payload.source]
    cached = cache_lookup(payload.external_id)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail="This search result has expired — run the search again and import it right away.",
        )

    try:
        job, _created = await _get_or_create_external_job(cached, payload.source, current_user.id, db)
    except Exception:
        raise HTTPException(status_code=409, detail="This job was already imported.")
    await _ensure_match(job, current_user.id, db)
    return await _attach_match(job, current_user.id, db)


def _profile_search_query(profile: CareerProfile) -> Optional[str]:
    """Best-effort search term derived from a saved career profile: the
    headline (usually a target job title) first, then the most recent
    listed role, then a handful of top skills — whichever is available
    first, since the free-text `q` providers accept is a single string."""
    if profile.headline and profile.headline.strip():
        return profile.headline.strip()
    for entry in profile.experience or []:
        title = (entry or {}).get("title")
        if title and str(title).strip():
            return str(title).strip()
    skill_names = [s.get("name") for s in (profile.skills or []) if isinstance(s, dict) and s.get("name")]
    if skill_names:
        return ", ".join(skill_names[:3])
    return None


_HOME_QUEUE_TARGET = 30  # Home's swipe queue is topped up to this many undecided matches, never left to grow past it.
_AUTO_IMPORT_LIMIT = 20  # Hard ceiling per sweep regardless of queue headroom, so one run can't dump 30 at once.


async def _undecided_queue_size(user_id: UUID, db: AsyncSession) -> int:
    """How many jobs are currently sitting in this user's Home queue —
    matched but not yet swiped on. Same shape as GET /matches' own count
    query, kept separate since that endpoint also supports a min_score
    filter this one doesn't need."""
    decided_job_ids_subq = select(Application.job_id).where(Application.user_id == user_id)
    count_stmt = (
        select(func.count())
        .select_from(JobMatch)
        .where(JobMatch.user_id == user_id, JobMatch.job_id.not_in(decided_job_ids_subq))
    )
    return (await db.execute(count_stmt)).scalar_one()


async def run_auto_import_for_user(user: User, db: AsyncSession) -> AutoImportResponse:
    """Searches every no-auth provider using the saved career profile
    (headline, most recent role, or top skills) and imports the newest
    matches straight into `jobs` with a computed match score — this is
    what runs right after a CV-derived profile is saved, on every pull-to-
    refresh, and on the every-2-hours scheduled sweep, so Home's swipe
    queue has something to show without the user having to visit Discover
    first. Only genuinely new postings are counted/matched; ones already
    in the database (by source_url) are left alone.

    Tops the queue up to `_HOME_QUEUE_TARGET` (30) rather than always
    adding up to `_AUTO_IMPORT_LIMIT` more — a user who swipes slower than
    the 2-hour sweep would otherwise see the queue grow without bound;
    this keeps it capped so there's always a fresh batch waiting without
    ever overflowing.

    Extracted from the route handler below so the same logic can also run
    unattended — see app/scripts/run_daily_sweep.py, invoked on a schedule
    (scripts/install-job-sweep-schedule.ps1) so new matches show up (with a
    push notification) even if the app was never opened that day."""
    profile = (
        await db.execute(select(CareerProfile).where(CareerProfile.user_id == user.id))
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=400, detail="Save your career profile before auto-searching for matches.")

    q = _profile_search_query(profile)
    if not q:
        raise HTTPException(
            status_code=400,
            detail="Add a headline, a recent role, or a few skills to your profile first so we know what to search for.",
        )

    current_queue_size = await _undecided_queue_size(user.id, db)
    room = max(0, _HOME_QUEUE_TARGET - current_queue_size)
    import_limit = min(room, _AUTO_IMPORT_LIMIT)

    if import_limit == 0:
        return AutoImportResponse(imported=0, query=q, sources=[])

    outcomes = await asyncio.gather(
        *[_run_search_provider(p, q, None, None, None, None) for p in _SEARCH_PROVIDERS]
    )

    all_results: list[ExternalJobResult] = []
    sources: list[AggregateSourceStatus] = []
    for provider, results, error in outcomes:
        all_results.extend(results)
        sources.append(AggregateSourceStatus(provider=provider, count=len(results), error=error))
    all_results.sort(key=_aggregate_sort_key, reverse=True)
    # Matters even more here than in the search endpoint: without it the
    # sweep imports each board's copy of one vacancy as its own `jobs` row,
    # so Home asks the user to swipe on the same job three times. The
    # existing source_url check in _get_or_create_external_job only catches
    # copies that happen to share a URL.
    all_results = dedupe_external_results(all_results)

    imported = 0
    # Walk the FULL sorted list (not a pre-sliced all_results[:import_limit])
    # and stop once import_limit NEW jobs are actually in — slicing first
    # was the bug: across repeated 2-hour sweeps against the same
    # profile-based query, the newest-first top of the list is dominated by
    # postings already imported in earlier sweeps, so a pre-slice mostly
    # re-examined duplicates and imported far fewer than import_limit even
    # though plenty of never-seen postings existed further down the list.
    for result in all_results:
        if imported >= import_limit:
            break
        try:
            job, created = await _get_or_create_external_job(
                result.model_dump(), result.source, user.id, db
            )
        except Exception:
            continue
        if not created:
            continue
        # use_llm=False: this loop can run once per newly-discovered job in
        # a single sweep — keep it on the free, offline semantic scorer
        # rather than firing one Anthropic call per job serially. On-demand
        # single-job matches (_ensure_match above, GET /jobs/{id}/match)
        # keep the higher-quality LLM default.
        await compute_and_persist_match(profile, job, user.id, db, use_llm=False)
        imported += 1

    if imported > 0 and push_notifications.is_configured():
        from firebase_admin import messaging

        tokens = (
            await db.execute(select(DeviceToken.token).where(DeviceToken.user_id == user.id))
        ).scalars().all()
        plural = "s" if imported != 1 else ""
        dead_tokens: list[str] = []
        for device_token in tokens:
            try:
                push_notifications.send_push(
                    device_token,
                    "JobPilot",
                    f"Encontramos {imported} vacante{plural} nueva{plural} que hacen match — ya están en tu cola.",
                )
            except messaging.UnregisteredError:
                dead_tokens.append(device_token)
        if dead_tokens:
            # A dead token failing here must never affect imported/matches
            # already committed above — this cleanup is best-effort and
            # isolated from the rest of the sweep's outcome.
            await db.execute(delete(DeviceToken).where(DeviceToken.token.in_(dead_tokens)))
            await db.commit()

    return AutoImportResponse(imported=imported, query=q, sources=sources)


@router.post("/jobs/search/auto-import", response_model=AutoImportResponse)
@limiter.limit("10/minute")
async def auto_import_matching_jobs(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutoImportResponse:
    return await run_auto_import_for_user(current_user, db)


@router.get("/jobs/{job_id}", response_model=JobSchema)
async def get_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobSchema:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return await _attach_match(job, current_user.id, db)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    await db.delete(job)
    await db.commit()
