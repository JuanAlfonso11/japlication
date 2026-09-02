from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.career_profile import CareerProfile
from app.models.enums import GenerationSource
from app.models.job import Job
from app.models.resume_version import ResumeVersion
from app.models.user import User
from app.schemas.resume_version import ResumeGenerateRequest
from app.schemas.resume_version import ResumeVersion as ResumeVersionSchema
from app.services.resume_adapter import adapt_resume

router = APIRouter(tags=["resumes"])


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


@router.get("/resume-versions/{resume_version_id}", response_model=ResumeVersionSchema)
async def get_resume_version(
    resume_version_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeVersionSchema:
    row = (
        await db.execute(
            select(ResumeVersion).where(
                ResumeVersion.id == resume_version_id, ResumeVersion.user_id == current_user.id
            )
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
