# NOTE: the AI / PDF / SMTP helpers below are synchronous by design, but
# uvicorn runs one event loop: calling one directly from an `async def`
# handler freezes EVERY other request for its whole duration (5-15s for a
# Claude call, up to the SMTP timeout for a slow mail server). They are
# dispatched with asyncio.to_thread so only the calling request waits -
# the same pattern services/match_engine.py already documents.
import asyncio
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.application import Application
from app.models.career_profile import CareerProfile
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.user import User
from app.schemas.job import Job as JobSchema
from app.schemas.job import JobListResponse, annotate_work_auth
from app.services import work_authorization
from app.models.enums import ApplicationStatus
from app.schemas.interview_prep import InterviewPrepResponse
from app.schemas.job_match import MatchResult, SkillGapsResponse
from app.services.interview_prep import build_interview_prep
from app.services.match_engine import compute_and_persist_match
from app.services.skill_gaps import aggregate_skill_gaps, summarize

router = APIRouter(tags=["match"])

# Statuses that mean "the user wanted this job", i.e. everything from a
# right swipe onward. `queued` is excluded (not decided yet) and so is
# `passed` (decided against) — counting either would dilute the signal with
# postings the user never actually wanted.
_INTERESTED_STATUSES = [
    ApplicationStatus.saved,
    ApplicationStatus.applied,
    ApplicationStatus.interviewing,
    ApplicationStatus.offer,
    # Kept deliberately: a rejection doesn't mean the user didn't want the
    # role, and those are often the most informative gaps of all.
    ApplicationStatus.rejected,
]

# Below this, percentages are noise ("100% of your 1 saved job") — so the
# aggregate falls back to every scored posting and says that it did.
_MIN_INTERESTED_JOBS = 4


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
    # Ni las que la empresa ya cerro (services/liveness.py) ni las que pasaron
    # su fecha limite: un swipe a la derecha ahi es tiempo perdido.
    still_open = (Job.closed_at.is_(None)) & (
        Job.deadline.is_(None) | (Job.deadline >= func.current_date())
    )

    stmt = (
        select(Job, JobMatch)
        .join(JobMatch, (JobMatch.job_id == Job.id) & (JobMatch.user_id == current_user.id))
        .where(Job.id.not_in(decided_job_ids_subq))
        .where(still_open)
    )
    if min_score is not None:
        stmt = stmt.where(JobMatch.overall_score >= min_score)

    count_stmt = (
        select(Job.id)
        .join(JobMatch, (JobMatch.job_id == Job.id) & (JobMatch.user_id == current_user.id))
        .where(Job.id.not_in(decided_job_ids_subq))
        .where(still_open)
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

    annotate_work_auth(items, await work_authorization.user_country(db, current_user.id))
    return JobListResponse(items=items, total=total)


@router.get("/match/skill-gaps", response_model=SkillGapsResponse)
async def get_skill_gaps(
    limit: int = Query(8, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillGapsResponse:
    """The skills that keep costing this user points, across the jobs they
    actually wanted.

    Per-job match results already say why one posting scored what it did;
    this is the pattern across them, which is what tells you what to learn
    next. Read-only and derived entirely from data the match engine already
    persisted, so it costs one query and never calls an LLM.
    """
    interested = (
        select(JobMatch.missing_skills)
        .join(
            Application,
            (Application.job_id == JobMatch.job_id)
            & (Application.user_id == JobMatch.user_id),
        )
        .where(
            JobMatch.user_id == current_user.id,
            Application.status.in_(_INTERESTED_STATUSES),
        )
    )
    rows = (await db.execute(interested)).scalars().all()

    based_on_all = False
    if len(rows) < _MIN_INTERESTED_JOBS:
        # Not enough decisions yet to talk about "what you're interested in".
        # Every scored posting is a weaker signal (it includes roles the user
        # would never take), but it beats an empty card for a new user — and
        # the flag lets the UI phrase it honestly.
        based_on_all = True
        rows = (
            (
                await db.execute(
                    select(JobMatch.missing_skills).where(JobMatch.user_id == current_user.id)
                )
            )
            .scalars()
            .all()
        )

    gaps, jobs_considered = aggregate_skill_gaps(rows, limit=limit)

    return SkillGapsResponse(
        gaps=gaps,
        jobs_considered=jobs_considered,
        based_on_all_matches=based_on_all,
        summary=summarize(gaps, jobs_considered) if not based_on_all else None,
    )


@router.post("/jobs/{job_id}/interview-prep", response_model=InterviewPrepResponse)
@limiter.limit("20/hour")
async def get_interview_prep(
    request: Request,
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewPrepResponse:
    """The questions this specific posting is likely to produce, and what in
    the user's own history answers them.

    The app already finds the job, scores it, tailors the CV and drafts the
    letter — and then stopped right where the hard part starts. Grounded in
    the profile and the cached match: talking points come from bullets the
    user actually wrote, and a skill they lack is presented as a gap to
    prepare for honestly rather than an answer to fake.

    Rate-limited because the AI path costs money; the rule-based fallback
    below it needs no key and is the default.
    """
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    profile = await _get_profile_or_400(current_user.id, db)

    # Reuse the cached match rather than recomputing: it already knows which
    # skills line up and which don't, which is the entire input here.
    match_row = (
        await db.execute(
            select(JobMatch).where(JobMatch.user_id == current_user.id, JobMatch.job_id == job_id)
        )
    ).scalar_one_or_none()
    if match_row is None:
        match_row = await compute_and_persist_match(profile, job, current_user.id, db)

    prep = await asyncio.to_thread(
        build_interview_prep,
        profile,
        job,
        list(match_row.matched_skills or []),
        list(match_row.missing_skills or []),
    )
    return InterviewPrepResponse(**prep)
