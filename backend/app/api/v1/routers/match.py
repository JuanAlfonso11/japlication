from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.application import Application
from app.models.career_profile import CareerProfile
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.user import User
from app.schemas.job import Job as JobSchema
from app.schemas.job import JobListResponse
from app.schemas.job_match import MatchResult
from app.services.match_engine import compute_and_persist_match

router = APIRouter(tags=["match"])


async def _get_profile_or_400(user_id: UUID, db: AsyncSession) -> CareerProfile:
    result = await db.execute(select(CareerProfile).where(CareerProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=400, detail="Create your career profile before computing matches."
        )
    return profile


@router.get("/jobs/{job_id}/match", response_model=MatchResult)
async def get_job_match(
    job_id: UUID,
    refresh: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatchResult:
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    if not refresh:
        existing = (
            await db.execute(
                select(JobMatch).where(JobMatch.user_id == current_user.id, JobMatch.job_id == job_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return MatchResult.model_validate(existing)

    profile = await _get_profile_or_400(current_user.id, db)
    match_row = await compute_and_persist_match(profile, job, current_user.id, db)
    return MatchResult.model_validate(match_row)


@router.get("/matches", response_model=JobListResponse)
async def list_match_queue(
    min_score: Optional[float] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobListResponse:
    # Exclude jobs the user has already swiped/decided on.
    decided_job_ids_subq = select(Application.job_id).where(Application.user_id == current_user.id)

    stmt = (
        select(Job, JobMatch)
        .join(JobMatch, (JobMatch.job_id == Job.id) & (JobMatch.user_id == current_user.id))
        .where(Job.id.not_in(decided_job_ids_subq))
    )
    if min_score is not None:
        stmt = stmt.where(JobMatch.overall_score >= min_score)

    count_stmt = (
        select(Job.id)
        .join(JobMatch, (JobMatch.job_id == Job.id) & (JobMatch.user_id == current_user.id))
        .where(Job.id.not_in(decided_job_ids_subq))
    )
    if min_score is not None:
        count_stmt = count_stmt.where(JobMatch.overall_score >= min_score)
    total = len((await db.execute(count_stmt)).all())

    stmt = stmt.order_by(JobMatch.overall_score.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).all()

    items = []
    for job, job_match in rows:
        schema = JobSchema.model_validate(job)
        schema.match = MatchResult.model_validate(job_match)
        items.append(schema)

    return JobListResponse(items=items, total=total)
