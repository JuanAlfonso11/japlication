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
from app.models.oauth_connection import OAuthConnection
from app.schemas.job import Job as JobSchema
from app.schemas.job import (
    ExternalJobImportRequest,
    ExternalJobResult,
    ExternalJobsSearchResponse,
    JobCreate,
    JobImportRequest,
    JobListResponse,
)
from app.schemas.job_match import MatchResult
from app.services import google_jobs, himalayas, upwork
from app.services.job_importer import import_job_from_url

router = APIRouter(tags=["jobs"])

# Every JobSource enum value that comes from a live search provider (as
# opposed to url_import/manual) maps to the service module that handles it.
_SEARCH_PROVIDERS = {"google_jobs", "himalayas", "upwork"}


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


async def _get_upwork_access_token(user_id: UUID, db: AsyncSession) -> str:
    result = await db.execute(
        select(OAuthConnection).where(OAuthConnection.user_id == user_id, OAuthConnection.provider == "upwork")
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        raise HTTPException(
            status_code=409,
            detail="Conecta tu cuenta de Upwork primero (POST /integrations/upwork/authorize).",
        )

    now = datetime.now(timezone.utc)
    if connection.expires_at is not None and connection.expires_at <= now and connection.refresh_token:
        try:
            refreshed = await upwork.refresh_access_token(connection.refresh_token)
        except upwork.UpworkError as exc:
            raise HTTPException(status_code=502, detail=f"Could not refresh Upwork token: {exc}") from exc
        connection.access_token = refreshed["access_token"]
        connection.refresh_token = refreshed.get("refresh_token") or connection.refresh_token
        connection.expires_at = refreshed.get("expires_at")
        await db.commit()

    return connection.access_token


@router.get("/jobs/search", response_model=ExternalJobsSearchResponse)
async def search_jobs(
    provider: str = Query("himalayas", pattern="^(himalayas|google_jobs|upwork)$"),
    q: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    hl: Optional[str] = Query(None),
    gl: Optional[str] = Query(None),
    next_page_token: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    worldwide: Optional[bool] = Query(None),
    seniority: Optional[str] = Query(None),
    employment_type: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExternalJobsSearchResponse:
    """Live-search one of three external providers. Nothing is persisted —
    pick a result and call POST /jobs/search/import to add it to `jobs`.

    - himalayas (default): free, no API key, remote-only listings.
    - google_jobs: requires SERPAPI_API_KEY (backend .env).
    - upwork: requires the user to connect their account first (see
      /integrations/upwork/*); freelance/contract postings.
    """
    if provider == "himalayas":
        try:
            data = await himalayas.search_himalayas_jobs(
                q=q,
                country=country,
                worldwide=worldwide,
                seniority=seniority,
                employment_type=employment_type,
                sort=sort,
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

    if provider == "google_jobs":
        if not q:
            raise HTTPException(status_code=422, detail="q is required for provider=google_jobs")
        try:
            data = await google_jobs.search_google_jobs(q=q, location=location, hl=hl, gl=gl, next_page_token=next_page_token)
        except google_jobs.GoogleJobsError as exc:
            detail = str(exc)
            status_code = 503 if "SERPAPI_API_KEY is not configured" in detail else 502
            raise HTTPException(status_code=status_code, detail=detail) from exc
        results = [
            ExternalJobResult(external_id=r["google_job_id"], **{k: v for k, v in r.items() if k != "google_job_id"})
            for r in data["results"]
            if r.get("google_job_id")
        ]
        return ExternalJobsSearchResponse(
            provider="google_jobs",
            results=results,
            next_page_token=data["next_page_token"],
            has_more=bool(data["next_page_token"]),
        )

    # provider == "upwork"
    access_token = await _get_upwork_access_token(current_user.id, db)
    skills = [s.strip() for s in (q or "").split(",") if s.strip()] if q and "," in q else None
    try:
        data = await upwork.search_upwork_jobs(access_token, q=None if skills else q, skills=skills)
    except PermissionError:
        # Access token rejected outright (not just past our tracked expiry) — refresh once and retry.
        result = await db.execute(
            select(OAuthConnection).where(OAuthConnection.user_id == current_user.id, OAuthConnection.provider == "upwork")
        )
        connection = result.scalar_one_or_none()
        if connection is None or not connection.refresh_token:
            raise HTTPException(status_code=409, detail="Tu conexión con Upwork expiró — reconéctala.") from None
        try:
            refreshed = await upwork.refresh_access_token(connection.refresh_token)
        except upwork.UpworkError as exc:
            raise HTTPException(status_code=502, detail=f"Could not refresh Upwork token: {exc}") from exc
        connection.access_token = refreshed["access_token"]
        connection.refresh_token = refreshed.get("refresh_token") or connection.refresh_token
        connection.expires_at = refreshed.get("expires_at")
        await db.commit()
        try:
            data = await upwork.search_upwork_jobs(connection.access_token, q=None if skills else q, skills=skills)
        except (PermissionError, upwork.UpworkError) as exc:
            raise HTTPException(status_code=502, detail=f"Upwork search failed: {exc}") from exc
    except upwork.UpworkError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    results = [
        ExternalJobResult(external_id=r["upwork_job_id"], **{k: v for k, v in r.items() if k != "upwork_job_id"})
        for r in data["results"]
        if r.get("upwork_job_id")
    ]
    return ExternalJobsSearchResponse(provider="upwork", results=results, has_more=data["has_more"])


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
        "google_jobs": google_jobs.get_cached_result,
        "himalayas": himalayas.get_cached_result,
        "upwork": upwork.get_cached_result,
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
