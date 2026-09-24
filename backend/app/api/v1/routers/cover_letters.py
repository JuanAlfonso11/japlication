# NOTE: the AI / PDF / SMTP helpers below are synchronous by design, but
# uvicorn runs one event loop: calling one directly from an `async def`
# handler freezes EVERY other request for its whole duration (5-15s for a
# Claude call, up to the SMTP timeout for a slow mail server). They are
# dispatched with asyncio.to_thread so only the calling request waits -
# the same pattern services/match_engine.py already documents.
import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.career_profile import CareerProfile
from app.models.cover_letter import CoverLetter
from app.models.enums import GenerationSource
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.resume_version import ResumeVersion
from app.models.user import User
from app.schemas.cover_letter import CoverLetter as CoverLetterSchema
from app.schemas.cover_letter import CoverLetterGenerateRequest
from app.services.cover_letter_generator import generate_cover_letter
from app.services.cover_letter_pdf import render_cover_letter_pdf

router = APIRouter(tags=["cover-letters"])


@router.post(
    "/jobs/{job_id}/cover-letter", response_model=CoverLetterSchema, status_code=status.HTTP_201_CREATED
)
async def generate_cover_letter_endpoint(
    job_id: UUID,
    payload: CoverLetterGenerateRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CoverLetterSchema:
    payload = payload or CoverLetterGenerateRequest()

    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="No encontramos esa vacante.")

    profile = (
        await db.execute(select(CareerProfile).where(CareerProfile.user_id == current_user.id))
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=400, detail="Primero sube tu CV en Perfil y guárdalo: de ahí sale la carta."
        )

    if payload.resume_version_id is not None:
        resume_version = (
            await db.execute(
                select(ResumeVersion).where(
                    ResumeVersion.id == payload.resume_version_id,
                    ResumeVersion.user_id == current_user.id,
                )
            )
        ).scalar_one_or_none()
        if resume_version is None:
            raise HTTPException(status_code=404, detail="No encontramos ese CV.")

    match_row = (
        await db.execute(
            select(JobMatch).where(JobMatch.user_id == current_user.id, JobMatch.job_id == job_id)
        )
    ).scalar_one_or_none()
    matched_skills = list(match_row.matched_skills) if match_row else []

    tone = payload.tone or "professional"
    generated = await asyncio.to_thread(
        generate_cover_letter,
        profile=profile,
        job=job,
        candidate_name=current_user.full_name,
        matched_skills=matched_skills,
        tone=tone,
    )

    cover_letter = CoverLetter(
        user_id=current_user.id,
        job_id=job.id,
        resume_version_id=payload.resume_version_id,
        content=generated["content"],
        tone=generated["tone"],
        generated_by=GenerationSource(generated["generated_by"]),
    )
    db.add(cover_letter)
    await db.commit()
    await db.refresh(cover_letter)
    return CoverLetterSchema.model_validate(cover_letter)


@router.get("/cover-letters", response_model=list[CoverLetterSchema])
async def list_cover_letters(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CoverLetterSchema]:
    rows = (
        await db.execute(
            select(CoverLetter)
            .options(selectinload(CoverLetter.job))
            .where(CoverLetter.user_id == current_user.id)
            .order_by(CoverLetter.created_at.desc())
        )
    ).scalars().all()
    return [CoverLetterSchema.model_validate(r) for r in rows]


@router.get("/cover-letters/{cover_letter_id}", response_model=CoverLetterSchema)
async def get_cover_letter(
    cover_letter_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CoverLetterSchema:
    row = (
        await db.execute(
            select(CoverLetter)
            .options(selectinload(CoverLetter.job))
            .where(CoverLetter.id == cover_letter_id, CoverLetter.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No encontramos esa carta.")
    return CoverLetterSchema.model_validate(row)


@router.get("/cover-letters/{cover_letter_id}/export/pdf")
async def export_cover_letter_pdf(
    cover_letter_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    row = (
        await db.execute(
            select(CoverLetter).where(
                CoverLetter.id == cover_letter_id, CoverLetter.user_id == current_user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No encontramos esa carta.")

    profile = (
        await db.execute(select(CareerProfile).where(CareerProfile.user_id == current_user.id))
    ).scalar_one_or_none()
    contact_info = profile.contact_info if profile is not None else {}

    pdf_bytes = await asyncio.to_thread(
        render_cover_letter_pdf,
        full_name=current_user.full_name,
        contact_info=contact_info,
        content=row.content,
        email=current_user.email,
    )
    filename = f"cover-letter-{row.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
