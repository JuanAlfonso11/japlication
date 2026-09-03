import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.application import Application
from app.models.enums import ApplicationStatus, JobSource
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.user import User
from app.schemas.job import Job as JobSchema
from app.schemas.job import (
    AggregateSearchResponse,
    AggregateSourceStatus,
    ExternalJobImportRequest,
    ExternalJobResult,
    ExternalJobsSearchResponse,
    JobCreate,
    JobImportRequest,
    JobListResponse,
)
from app.schemas.job_match import MatchResult
from app.services import (
    arbeitnow,
    experience_level,
    himalayas,
    jobicy,
    remotejobs_org,
    remotive,
    themuse,
)
from app.services.job_importer import import_job_from_url

router = APIRouter(tags=["jobs"])

# Every JobSource enum value that comes from a live search provider (as
# opposed to url_import/manual). All of these are free, no-auth APIs — see
# docs/PUBLIC_APIS_RESEARCH.md for what was investigated and why Google
# Jobs/Upwork/LinkedIn/Indeed aren't (and, for LinkedIn/Indeed, can't be)
# part of this list.
_SEARCH_PROVIDERS = {"himalayas", "arbeitnow", "remotive", "jobicy", "remotejobs_org", "themuse"}

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
            return await _attach_match(existing_job, current_user.id, db)
        raise HTTPException(status_code=422, detail="could not parse job posting")
    await db.refresh(job)
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
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
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

    items = [await _attach_match(job, current_user.id, db) for job in jobs]
    return JobListResponse(items=items, total=total)


@router.get("/jobs/search", response_model=ExternalJobsSearchResponse)
async def search_jobs(
    provider: str = Query(
        "himalayas",
        pattern="^(himalayas|arbeitnow|remotive|jobicy|remotejobs_org|themuse)$",
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
    """Live-search one no-auth provider. Nothing is persisted — pick a
    result and call POST /jobs/search/import to add it to `jobs`.

    See GET /jobs/search/aggregate to query all six providers in one call,
    which is what Discover uses by default.
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

    # provider == "themuse"
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


async def _run_no_auth_provider(
    provider: str,
    q: Optional[str],
    location: Optional[str],
    experience_level_filter: Optional[str],
    remote_type_filter: Optional[str],
    category: Optional[str],
) -> tuple[str, list[ExternalJobResult], Optional[str]]:
    """Runs one no-auth provider search and normalizes both its results and
    any failure into a uniform (provider, results, error) tuple, so one
    provider erroring never breaks the others in the aggregate fan-out."""
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
async def search_jobs_aggregate(
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
    """Fans out to every no-auth job-search provider at once
    (Himalayas, Arbeitnow, Remotive, Jobicy, RemoteJobs.org, The Muse) and
    merges the results into one list, newest first — this is what the
    Discover tab's "search all sources" action calls. A provider that
    errors doesn't take the others down with it: its failure shows up
    in `sources` instead of the result list. `location` is purely geographic
    (e.g. "Mexico"); `remote_type` (remote/hybrid/onsite) is independent and
    defaults to "remote" to preserve the historical default of showing only
    remote-friendly postings when no filters are set."""
    outcomes = await asyncio.gather(
        *[
            _run_no_auth_provider(p, q, location, experience_level_filter, remote_type_filter, category)
            for p in _SEARCH_PROVIDERS
        ]
    )

    all_results: list[ExternalJobResult] = []
    sources: list[AggregateSourceStatus] = []
    for provider, results, error in outcomes:
        all_results.extend(results)
        sources.append(AggregateSourceStatus(provider=provider, count=len(results), error=error))

    all_results.sort(key=_aggregate_sort_key, reverse=True)
    return AggregateSearchResponse(results=all_results, sources=sources)


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
    }[payload.source]
    cached = cache_lookup(payload.external_id)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail="This search result has expired — run the search again and import it right away.",
        )

    if cached.get("source_url"):
        existing = await db.execute(select(Job).where(Job.source_url == cached["source_url"]))
        existing_job = existing.scalar_one_or_none()
        if existing_job is not None:
            return await _attach_match(existing_job, current_user.id, db)

    job = Job(
        imported_by=current_user.id,
        source=JobSource(payload.source),
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
                return await _attach_match(existing_job, current_user.id, db)
        raise HTTPException(status_code=409, detail="This job was already imported.")
    await db.refresh(job)
    return await _attach_match(job, current_user.id, db)


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
