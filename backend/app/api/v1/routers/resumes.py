from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.career_profile import CareerProfile
from app.models.enums import GenerationSource
from app.models.job import Job
from app.models.resume_version import ResumeVersion
from app.models.user import User
from app.schemas.resume_version import ReusableResumeSuggestion
from app.schemas.resume_version import ResumeGenerateRequest
from app.schemas.resume_version import ResumeVersion as ResumeVersionSchema
from app.services.resume_adapter import adapt_resume
from app.services.skills_taxonomy import canonical_skill_set

router = APIRouter(tags=["resumes"])

# Below this Jaccard overlap (on canonicalized required-skill names), two
# jobs are considered different enough that reusing one job's tailored
# resume for the other would misrepresent the fit — so the reuse
# suggestion stays empty rather than pushing a bad match.
_REUSE_SIMILARITY_THRESHOLD = 0.5


def _required_skill_names(job: Job) -> set[str]:
    names = [
        entry.get("name")
        for entry in (job.skills_required or [])
        if isinstance(entry, dict) and entry.get("name")
    ]
    return canonical_skill_set(names)


async def _find_reusable_resume(
    db: AsyncSession, user_id: UUID, job: Job
) -> tuple[Optional[ResumeVersion], float, Optional[Job]]:
    target_skills = _required_skill_names(job)
    if not target_skills:
        return None, 0.0, None

    rows = (
        await db.execute(
            select(ResumeVersion, Job)
            .join(Job, Job.id == ResumeVersion.job_id)
            .where(ResumeVersion.user_id == user_id, ResumeVersion.job_id != job.id)
            .order_by(ResumeVersion.created_at.desc())
        )
    ).all()

    best: Optional[ResumeVersion] = None
    best_score = 0.0
    best_job: Optional[Job] = None
    for resume_version, source_job in rows:
        source_skills = _required_skill_names(source_job)
        if not source_skills:
            continue
        union = target_skills | source_skills
        score = len(target_skills & source_skills) / len(union) if union else 0.0
        if score > best_score:
            best, best_score, best_job = resume_version, score, source_job

    if best is not None and best_score >= _REUSE_SIMILARITY_THRESHOLD:
        return best, best_score, best_job
    return None, 0.0, None


@router.get("/jobs/{job_id}/resume/reusable", response_model=ReusableResumeSuggestion)
async def suggest_reusable_resume(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReusableResumeSuggestion:
    """Looks for an already-generated resume from a *different* job whose
    required skills overlap enough (>= 50% Jaccard) with this job's that
    it's worth reusing as-is instead of generating (and storing) another
    near-duplicate version — several jobs often ask for the same stack."""
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    resume_version, similarity, source_job = await _find_reusable_resume(db, current_user.id, job)
    return ReusableResumeSuggestion(
        resume_version=ResumeVersionSchema.model_validate(resume_version) if resume_version else None,
        similarity=round(similarity, 2),
        source_job_title=source_job.title if source_job else None,
        source_company=source_job.company if source_job else None,
    )


@router.post(
    "/jobs/{job_id}/resume", response_model=ResumeVersionSchema, status_code=status.HTTP_201_CREATED
)
async def generate_resume(
    job_id: UUID,
    payload: ResumeGenerateRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeVersionSchema:
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    profile = (
        await db.execute(select(CareerProfile).where(CareerProfile.user_id == current_user.id))
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=400, detail="Create your career profile before generating a resume.")

    adapted = adapt_resume(profile, job)

    resume_version = ResumeVersion(
        user_id=current_user.id,
        career_profile_id=profile.id,
        job_id=job.id,
        title=f"{job.title} @ {job.company}",
        content=adapted["content"],
        change_log=adapted["change_log"],
        generated_by=GenerationSource(adapted["generated_by"]),
    )
    db.add(resume_version)
    await db.commit()
    await db.refresh(resume_version)
    return ResumeVersionSchema.model_validate(resume_version)


@router.get("/resume-versions", response_model=list[ResumeVersionSchema])
async def list_resume_versions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ResumeVersionSchema]:
    """Every tailored resume the user has generated, newest first — the
    "CVs usados" section in Profile, so the base profile stays visibly
    the single source of truth while each per-job adaptation (and its
    change_log of what was reordered/rephrased for that posting) stays
    inspectable on its own."""
    rows = (
        await db.execute(
            select(ResumeVersion)
            .options(selectinload(ResumeVersion.job))
            .where(ResumeVersion.user_id == current_user.id)
            .order_by(ResumeVersion.created_at.desc())
        )
    ).scalars().all()
    return [ResumeVersionSchema.model_validate(r) for r in rows]


@router.get("/resume-versions/{resume_version_id}", response_model=ResumeVersionSchema)
async def get_resume_version(
    resume_version_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeVersionSchema:
    row = (
        await db.execute(
            select(ResumeVersion)
            .options(selectinload(ResumeVersion.job))
            .where(ResumeVersion.id == resume_version_id, ResumeVersion.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Resume version not found.")
    return ResumeVersionSchema.model_validate(row)


def _render_ats_text(resume_version: ResumeVersion) -> str:
    content = resume_version.content or {}
    lines: list[str] = [resume_version.title, "=" * len(resume_version.title), ""]

    summary = content.get("summary")
    if summary:
        lines += ["SUMMARY", summary, ""]

    skills = content.get("skills") or []
    if skills:
        lines += ["SKILLS", ", ".join(skills), ""]

    experience = content.get("experience") or []
    if experience:
        lines.append("EXPERIENCE")
        for exp in experience:
            header = f"{exp.get('title', '')} — {exp.get('company', '')}".strip(" —")
            dates = f"{exp.get('start_date', '') or ''} - {exp.get('end_date') or 'Present'}"
            lines.append(f"{header} ({dates})")
            if exp.get("location"):
                lines.append(exp["location"])
            for bullet in exp.get("bullets") or []:
                lines.append(f"- {bullet}")
            lines.append("")

    education = content.get("education") or []
    if education:
        lines.append("EDUCATION")
        for edu in education:
            deg = f"{edu.get('degree', '')} in {edu.get('field', '')}".strip(" in")
            lines.append(f"{deg} — {edu.get('institution', '')}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


@router.get("/resume-versions/{resume_version_id}/export")
async def export_resume_version(
    resume_version_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    row = (
        await db.execute(
            select(ResumeVersion).where(
                ResumeVersion.id == resume_version_id, ResumeVersion.user_id == current_user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Resume version not found.")

    text = _render_ats_text(row)
    filename = f"resume-{row.id}.txt"
    return PlainTextResponse(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
