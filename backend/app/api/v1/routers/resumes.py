# NOTE: the AI / PDF / SMTP helpers below are synchronous by design, but
# uvicorn runs one event loop: calling one directly from an `async def`
# handler freezes EVERY other request for its whole duration (5-15s for a
# Claude call, up to the SMTP timeout for a slow mail server). They are
# dispatched with asyncio.to_thread so only the calling request waits -
# the same pattern services/match_engine.py already documents.
import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse, Response
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
from app.schemas.resume_version import ResumeVersionUpdate
from app.services.profile_i18n import detect_language, normalize_language
from app.services.resume_adapter import adapt_resume
from app.services.resume_latex import render_resume_latex
from app.services.resume_pdf import render_resume_pdf
from app.services.resume_text import render_resume_text
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
    db: AsyncSession, user_id: UUID, job: Job, language: str
) -> tuple[Optional[ResumeVersion], float, Optional[Job]]:
    target_skills = _required_skill_names(job)
    if not target_skills:
        return None, 0.0, None

    # Same-language only. A Spanish CV offered for an English posting is
    # worse than no suggestion at all: the skill overlap that made it look
    # reusable is exactly what hides the problem until it has been sent.
    rows = (
        await db.execute(
            select(ResumeVersion, Job)
            .join(Job, Job.id == ResumeVersion.job_id)
            .where(
                ResumeVersion.user_id == user_id,
                ResumeVersion.job_id != job.id,
                ResumeVersion.language == language,
            )
            .order_by(ResumeVersion.created_at.desc())
        )
    ).all()

    best: Optional[ResumeVersion] = None
    best_rank: tuple[int, float] = (0, 0.0)
    best_score = 0.0
    best_job: Optional[Job] = None
    for resume_version, source_job in rows:
        source_skills = _required_skill_names(source_job)
        if not source_skills:
            continue
        union = target_skills | source_skills
        score = len(target_skills & source_skills) / len(union) if union else 0.0
        if score < _REUSE_SIMILARITY_THRESHOLD:
            continue

        # Among versions that all clear the threshold, one the user actually
        # corrected beats a purely generated one even at somewhat lower skill
        # overlap: it carries their own wording, which is the whole point of
        # having edited it. Similarity still decides within each group, and a
        # version below the threshold is never offered either way.
        rank = (1 if resume_version.edited_at is not None else 0, score)
        if rank > best_rank:
            best, best_rank, best_score, best_job = resume_version, rank, score, source_job

    if best is not None:
        return best, best_score, best_job
    return None, 0.0, None


@router.get("/jobs/{job_id}/resume/reusable", response_model=ReusableResumeSuggestion)
async def suggest_reusable_resume(
    job_id: UUID,
    language: Optional[str] = None,
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

    code = normalize_language(language) if language else detect_language(job.description)
    resume_version, similarity, source_job = await _find_reusable_resume(
        db, current_user.id, job, code
    )
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

    # No explicit choice means "write it in the language the ad is in" --
    # the default a person would pick, and the one that keeps the CV
    # readable by whoever posted the job.
    language = (payload.language if payload else None) or detect_language(job.description)
    adapted = await asyncio.to_thread(adapt_resume, profile, job, language)

    resume_version = ResumeVersion(
        user_id=current_user.id,
        career_profile_id=profile.id,
        job_id=job.id,
        title=f"{job.title} @ {job.company}",
        content=adapted["content"],
        change_log=adapted["change_log"],
        language=adapted["language"],
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


@router.patch("/resume-versions/{resume_version_id}", response_model=ResumeVersionSchema)
async def update_resume_version(
    resume_version_id: UUID,
    payload: ResumeVersionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeVersionSchema:
    """Lets the user correct a generated resume before exporting it.

    Generated versions used to be read-only, so a bullet the adapter got
    wrong could only be fixed by editing the PDF afterwards — outside the
    app, and lost for next time. Editing here also stamps `edited_at`, which
    is what makes this version the preferred starting point when a later,
    similar posting looks for a resume to reuse: the correction is made once
    and carries forward.
    """
    row = (
        await db.execute(
            select(ResumeVersion)
            .options(selectinload(ResumeVersion.job))
            .where(ResumeVersion.id == resume_version_id, ResumeVersion.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Resume version not found.")

    if payload.title is not None:
        row.title = payload.title

    if payload.content is not None:
        # Copied, not mutated in place: SQLAlchemy tracks JSONB columns by
        # identity, so editing the existing dict would leave the change
        # invisible to the session and silently never persist.
        content = dict(row.content or {})

        if payload.content.summary is not None:
            content["summary"] = payload.content.summary
        if payload.content.skills is not None:
            content["skills"] = [s.strip() for s in payload.content.skills if s and s.strip()]

        if payload.content.experience_bullets is not None:
            experience = [dict(entry) for entry in (content.get("experience") or [])]
            for index, bullets in payload.content.experience_bullets.items():
                if index < 0 or index >= len(experience):
                    raise HTTPException(
                        status_code=400,
                        detail=f"No existe la experiencia en la posición {index}.",
                    )
                experience[index]["bullets"] = [b.strip() for b in bullets if b and b.strip()]
            content["experience"] = experience

        row.content = content

    row.edited_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return ResumeVersionSchema.model_validate(row)


def _render_ats_text(resume_version: ResumeVersion) -> str:
    """Plain-text twin of the PDF. The rendering lives in
    services/resume_text.py so the master CV export uses the same code."""
    return render_resume_text(
        title=resume_version.title,
        content=resume_version.content or {},
        language=resume_version.language,
    )


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
    filename = f"resume-{row.language}-{row.id}.txt"
    return PlainTextResponse(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/resume-versions/{resume_version_id}/export/tex")
async def export_resume_version_latex(
    resume_version_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """The same CV as LaTeX source, for compiling in Overleaf (or locally).

    Overleaf has no public compile API, so the server cannot hand back a
    PDF it built there — what it can do is produce the source, which the
    frontend posts straight into Overleaf's documented snippet endpoint so
    the user lands on an already-compiling document.

    The template is single-column with ordinary headings on purpose: fancy
    LaTeX CV classes are a common way to make a resume unparseable, which
    would undo the ATS work the direct-PDF export exists to guarantee. See
    services/resume_latex.py.
    """
    row = (
        await db.execute(
            select(ResumeVersion).where(
                ResumeVersion.id == resume_version_id, ResumeVersion.user_id == current_user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Resume version not found.")

    profile = (
        await db.execute(select(CareerProfile).where(CareerProfile.id == row.career_profile_id))
    ).scalar_one_or_none()

    source = render_resume_latex(
        full_name=current_user.full_name,
        contact_info=profile.contact_info if profile is not None else {},
        content=row.content,
        language=row.language,
        email=current_user.email,
    )
    filename = f"resume-{row.language}-{row.id}.tex"
    return PlainTextResponse(
        content=source,
        media_type="application/x-tex; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/resume-versions/{resume_version_id}/export/pdf")
async def export_resume_version_pdf(
    resume_version_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """A real, ATS-safe PDF (single column, standard headers, selectable
    text — see resume_pdf.py) meant to be uploaded to an external
    application form: most of them (Greenhouse, Lever, Workday, LinkedIn/
    Indeed Easy Apply) auto-fill name/contact/experience from an uploaded
    resume, which is the actual, buildable way to avoid retyping the same
    information on every site — there's no legitimate way to submit the
    application itself from here (see docs/PUBLIC_APIS_RESEARCH.md's
    LinkedIn section for why: every serious ATS gates its submission API
    behind employer-only credentials, Greenhouse included)."""
    row = (
        await db.execute(
            select(ResumeVersion).where(
                ResumeVersion.id == resume_version_id, ResumeVersion.user_id == current_user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Resume version not found.")

    profile = (
        await db.execute(select(CareerProfile).where(CareerProfile.id == row.career_profile_id))
    ).scalar_one_or_none()
    contact_info = profile.contact_info if profile is not None else {}

    pdf_bytes = await asyncio.to_thread(
        render_resume_pdf,
        full_name=current_user.full_name,
        contact_info=contact_info,
        content=row.content,
        language=row.language,
        email=current_user.email,
    )
    filename = f"resume-{row.language}-{row.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
