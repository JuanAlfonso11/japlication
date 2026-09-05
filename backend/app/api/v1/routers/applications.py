from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.application import Application
from app.models.career_profile import CareerProfile
from app.models.cover_letter import CoverLetter
from app.models.enums import ApplicationStatus, GenerationSource, SwipeDecision
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.resume_version import ResumeVersion
from app.models.user import User
from app.schemas.application import Application as ApplicationSchema
from app.schemas.application import ApplicationListResponse, ApplicationUpdate, DecisionRequest, JobSummary
from app.services.cover_letter_generator import generate_cover_letter

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


async def _reuse_or_generate_cover_letter(
    db: AsyncSession,
    current_user: User,
    job: Job,
    resume_version_id: Optional[UUID],
    match_row: Optional[JobMatch],
) -> Optional[UUID]:
    """Backs the "auto-send" behavior for jobs that require a cover letter:
    reuses the most recent one already generated for this exact job if
    there is one (e.g. the user generated it manually from the job-detail
    page before swiping), otherwise generates a fresh one from the
    profile. Returns None (never raises) when there's no career profile
    to generate from yet — a right swipe still goes through and applies,
    just without a cover letter attached, rather than blocking the swipe
    on an optional artifact."""
    reusable = (
        await db.execute(
            select(CoverLetter)
            .where(CoverLetter.user_id == current_user.id, CoverLetter.job_id == job.id)
            .order_by(CoverLetter.created_at.desc())
        )
    ).scalars().first()
    if reusable is not None:
        return reusable.id

    profile = (
        await db.execute(select(CareerProfile).where(CareerProfile.user_id == current_user.id))
    ).scalar_one_or_none()
    if profile is None:
        return None

    matched_skills = list(match_row.matched_skills) if match_row else []
    generated = generate_cover_letter(
        profile=profile,
        job=job,
        candidate_name=current_user.full_name,
        matched_skills=matched_skills,
        tone="professional",
    )
    cover_letter = CoverLetter(
        user_id=current_user.id,
        job_id=job.id,
        resume_version_id=resume_version_id,
        content=generated["content"],
        tone=generated["tone"],
        generated_by=GenerationSource(generated["generated_by"]),
    )
    db.add(cover_letter)
    await db.flush()
    return cover_letter.id


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

    resume_version_id = payload.resume_version_id
    if resume_version_id is not None:
        owned = (
            await db.execute(
                select(ResumeVersion.id).where(
                    ResumeVersion.id == resume_version_id, ResumeVersion.user_id == current_user.id
                )
            )
        ).scalar_one_or_none()
        if owned is None:
            raise HTTPException(status_code=404, detail="Resume version not found.")

    cover_letter_id = payload.cover_letter_id
    if cover_letter_id is not None:
        owned = (
            await db.execute(
                select(CoverLetter.id).where(
                    CoverLetter.id == cover_letter_id, CoverLetter.user_id == current_user.id
                )
            )
        ).scalar_one_or_none()
        if owned is None:
            raise HTTPException(status_code=404, detail="Cover letter not found.")

    # A right swipe IS the apply decision — for a job that requires a
    # cover letter, auto-attach one (reusing an existing one for this job
    # if there is one) unless the caller already provided one.
    already_attached = existing.cover_letter_id if existing else None
    if (
        new_status == ApplicationStatus.applied
        and job.requires_cover_letter
        and cover_letter_id is None
        and already_attached is None
    ):
        cover_letter_id = await _reuse_or_generate_cover_letter(
            db, current_user, job, resume_version_id, match_row
        )

    if existing is None:
        app_row = Application(
            user_id=current_user.id,
            job_id=job_id,
            status=new_status,
            decision=payload.decision,
            match_score=match_score,
            resume_version_id=resume_version_id,
            cover_letter_id=cover_letter_id,
            applied_at=applied_at,
        )
        db.add(app_row)
    else:
        existing.decision = payload.decision
        existing.status = new_status
        if match_score is not None:
            existing.match_score = match_score
        if resume_version_id is not None:
            existing.resume_version_id = resume_version_id
        if cover_letter_id is not None:
            existing.cover_letter_id = cover_letter_id
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


@router.get("/applications", response_model=ApplicationListResponse)
async def list_applications(
    status_filter: Optional[ApplicationStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationListResponse:
    stmt = select(Application).where(Application.user_id == current_user.id)
    count_stmt = select(func.count(Application.id)).where(Application.user_id == current_user.id)
    if status_filter is not None:
        stmt = stmt.where(Application.status == status_filter)
        count_stmt = count_stmt.where(Application.status == status_filter)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.options(selectinload(Application.job))
        .order_by(Application.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return ApplicationListResponse(items=[_serialize(r) for r in rows], total=total)


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


@router.delete("/applications/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def undo_application(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """"Deshacer" for a left swipe — only ever removes a `passed` decision,
    putting the job straight back in Home's queue (its JobMatch row was
    never touched, and GET /matches excludes only jobs with an existing
    Application). Deliberately does NOT allow undoing an `applied`
    decision this way: that already has real-world consequences (a cover
    letter may have been sent, it's tracked in the pipeline) and should go
    through PATCH (e.g. to `withdrawn`) instead of disappearing outright."""
    row = (
        await db.execute(
            select(Application).where(Application.id == application_id, Application.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    if row.status != ApplicationStatus.passed:
        raise HTTPException(
            status_code=400,
            detail="Only a passed job can be undone this way — update its status instead for an active application.",
        )
    await db.delete(row)
    await db.commit()
