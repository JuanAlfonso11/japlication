from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.application import Application
from app.models.enums import ApplicationStatus, SwipeDecision
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.user import User
from app.schemas.application import Application as ApplicationSchema
from app.schemas.application import ApplicationUpdate, DecisionRequest, JobSummary

router = APIRouter(tags=["applications"])

# A right swipe means "apply" — it goes straight to `applied` (with
# `applied_at` stamped below) rather than parking at `saved`, since the
# swipe itself is the user's application decision, not a bookmark step
# that needs a separate manual "mark as applied" action afterward.
DECISION_TO_STATUS = {
    SwipeDecision.right: ApplicationStatus.applied,
    SwipeDecision.left: ApplicationStatus.passed,
}


def _serialize(app_row: Application) -> ApplicationSchema:
    schema = ApplicationSchema.model_validate(app_row)
    if app_row.job is not None:
        schema.job = JobSummary.model_validate(app_row.job)
    return schema


@router.post("/jobs/{job_id}/decision", response_model=ApplicationSchema, status_code=status.HTTP_201_CREATED)
async def swipe_decision(
    job_id: UUID,
    payload: DecisionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationSchema:
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    match_score = None
    match_row = (
        await db.execute(
            select(JobMatch).where(JobMatch.user_id == current_user.id, JobMatch.job_id == job_id)
        )
    ).scalar_one_or_none()
    if match_row is not None:
        match_score = match_row.overall_score

    existing = (
        await db.execute(
            select(Application).where(Application.user_id == current_user.id, Application.job_id == job_id)
        )
    ).scalar_one_or_none()

    new_status = DECISION_TO_STATUS[payload.decision]
    applied_at = datetime.now(timezone.utc) if new_status == ApplicationStatus.applied else None

    if existing is None:
        app_row = Application(
            user_id=current_user.id,
            job_id=job_id,
            status=new_status,
            decision=payload.decision,
            match_score=match_score,
            applied_at=applied_at,
        )
        db.add(app_row)
    else:
        existing.decision = payload.decision
        existing.status = new_status
        if match_score is not None:
            existing.match_score = match_score
        if applied_at is not None and existing.applied_at is None:
            existing.applied_at = applied_at
        app_row = existing

    await db.commit()
    app_row = (
        await db.execute(
            select(Application)
            .options(selectinload(Application.job))
            .where(Application.id == app_row.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return _serialize(app_row)


@router.get("/applications", response_model=list[ApplicationSchema])
async def list_applications(
    status_filter: Optional[ApplicationStatus] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApplicationSchema]:
    stmt = (
        select(Application)
        .options(selectinload(Application.job))
        .where(Application.user_id == current_user.id)
        .order_by(Application.updated_at.desc())
    )
    if status_filter is not None:
        stmt = stmt.where(Application.status == status_filter)
    rows = (await db.execute(stmt)).scalars().all()
    return [_serialize(r) for r in rows]


@router.get("/applications/{application_id}", response_model=ApplicationSchema)
async def get_application(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationSchema:
    row = (
        await db.execute(
            select(Application)
            .options(selectinload(Application.job))
            .where(Application.id == application_id, Application.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return _serialize(row)


@router.patch("/applications/{application_id}", response_model=ApplicationSchema)
async def update_application(
    application_id: UUID,
    payload: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationSchema:
    row = (
        await db.execute(
            select(Application).where(Application.id == application_id, Application.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found.")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)

    await db.commit()
    row = (
        await db.execute(
            select(Application)
            .options(selectinload(Application.job))
            .where(Application.id == row.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return _serialize(row)
