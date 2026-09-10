from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.career_profile import CareerProfile
from app.models.user import User
from app.schemas.career_profile import CareerProfile as CareerProfileSchema
from app.schemas.career_profile import (
    CareerProfileUpsert,
    CVUploadResult,
    LanguageStatus,
    ProfileImprovementResult,
)
from app.schemas.cv_evaluation import CVEvaluation
from app.services import cv_upload
from app.services.cv_evaluator import evaluate_cv
from app.services.master_resume import master_resume_content
from app.services.profile_i18n import labels_for, normalize_language, translation_status
from app.services.profile_improver import improve_profile
from app.services.resume_latex import render_resume_latex
from app.services.resume_pdf import render_resume_pdf
from app.services.resume_text import render_resume_text

router = APIRouter(prefix="/profile", tags=["profile"])


# --- Master CV exports --------------------------------------------------------
# The whole profile as a downloadable CV, through the same three renderers the
# tailored CVs use (see services/master_resume.py). They export what is SAVED:
# the frontend disables the buttons while the form has unsaved edits, because a
# download that is silently the previous version is the one mistake here nobody
# notices until the file has already been sent.


async def _master_cv(
    db: AsyncSession, current_user: User, language: str | None
) -> tuple[CareerProfile, dict[str, Any], str]:
    result = await db.execute(select(CareerProfile).where(CareerProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Create your career profile before downloading it.")
    code = normalize_language(language)
    return profile, master_resume_content(profile, code), code


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


@router.get("/export")
async def export_master_cv_text(
    language: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """The master CV as plain text. `language` is "en" or "es"; anything else
    falls back to the base language instead of failing."""
    _profile, content, code = await _master_cv(db, current_user, language)
    return PlainTextResponse(
        content=render_resume_text(
            title=current_user.full_name or labels_for(code)["resume"],
            content=content,
            language=code,
        ),
        media_type="text/plain; charset=utf-8",
        headers=_attachment(f"cv-maestro-{code}.txt"),
    )


@router.get("/export/pdf")
async def export_master_cv_pdf(
    language: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The master CV as an ATS-safe PDF — see services/resume_pdf.py."""
    profile, content, code = await _master_cv(db, current_user, language)
    pdf_bytes = render_resume_pdf(
        full_name=current_user.full_name,
        contact_info=profile.contact_info or {},
        content=content,
        language=code,
        email=current_user.email,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=_attachment(f"cv-maestro-{code}.pdf"),
    )


@router.get("/export/tex")
async def export_master_cv_latex(
    language: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """The master CV as LaTeX source, for Overleaf — see services/resume_latex.py."""
    profile, content, code = await _master_cv(db, current_user, language)
    source = render_resume_latex(
        full_name=current_user.full_name,
        contact_info=profile.contact_info or {},
        content=content,
        language=code,
        email=current_user.email,
    )
    return PlainTextResponse(
        content=source,
        media_type="application/x-tex; charset=utf-8",
        headers=_attachment(f"cv-maestro-{code}.tex"),
    )


@router.get("", response_model=CareerProfileSchema)
async def get_profile(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> CareerProfileSchema:
    result = await db.execute(select(CareerProfile).where(CareerProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Career profile not created yet.")
    return CareerProfileSchema.model_validate(profile)


@router.put("", response_model=CareerProfileSchema)
async def upsert_profile(
    payload: CareerProfileUpsert,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CareerProfileSchema:
    result = await db.execute(select(CareerProfile).where(CareerProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()

    data = payload.model_dump(mode="json")

    # An older client that predates bilingual profiles does not send
    # `translations`, and Pydantic would fill in {} -- which would silently
    # wipe the Spanish CV of anyone still on the installed APK. Only write
    # the field when the request actually carried it.
    if "translations" not in payload.model_fields_set:
        data.pop("translations", None)

    if profile is None:
        profile = CareerProfile(user_id=current_user.id, **data)
        db.add(profile)
    else:
        for field, value in data.items():
            setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)
    return CareerProfileSchema.model_validate(profile)


@router.get("/languages", response_model=list[LanguageStatus])
async def get_profile_languages(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[LanguageStatus]:
    """Which languages this profile can already produce a full CV in.

    The completeness rule lives in profile_i18n.translation_status rather
    than in the frontend so the badge in the UI and the fallback the
    renderer actually performs can never disagree."""
    result = await db.execute(select(CareerProfile).where(CareerProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Career profile not created yet.")

    return [
        LanguageStatus(code=code, **status)
        for code, status in translation_status(profile).items()
    ]


@router.post("/improve", response_model=ProfileImprovementResult)
@limiter.limit("5/hour")
async def improve_profile_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ProfileImprovementResult:
    """Rewrites the base profile's headline/summary/experience-bullet
    wording for clarity and impact — same facts, better writing. This is
    the "agente" for the main CV; tailoring for a specific job stays a
    separate action (POST /jobs/{job_id}/resume). Nothing is persisted
    here — the frontend shows the proposal and the user still has to hit
    Save (PUT /profile) to keep it, same as CV upload."""
    result = await db.execute(select(CareerProfile).where(CareerProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Create your career profile before improving it.")

    improved = improve_profile(profile)
    return ProfileImprovementResult.model_validate(improved)


@router.get("/evaluation", response_model=CVEvaluation)
async def get_profile_evaluation(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> CVEvaluation:
    """Rule-based CV quality check — independent of any specific job: flags
    completeness gaps, unquantified/weak bullets, thin skills coverage, and
    ATS-safety issues, so the user knows what to fix before applying."""
    result = await db.execute(select(CareerProfile).where(CareerProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Create your career profile before evaluating it.")
    return CVEvaluation.model_validate(evaluate_cv(profile))


@router.post("/import-cv", response_model=CVUploadResult)
@limiter.limit("5/hour")
async def import_cv(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> CVUploadResult:
    """Parse an uploaded PDF resume into a draft CareerProfile. Nothing is
    persisted here — the frontend pre-fills the profile editor with the
    result and the user still has to review it and hit Save."""
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=422, detail="Please upload a PDF file.")

    max_bytes = settings.MAX_CV_UPLOAD_MB * 1024 * 1024

    # Read in chunks and stop the moment the limit is passed. `await
    # file.read()` with no argument pulls the WHOLE upload into memory
    # first and only then compares its length, so the 8 MB limit was
    # advisory: a 2 GB body was fully buffered before being rejected, which
    # is enough to take the container down on a box this size.
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"PDF is too large (max {settings.MAX_CV_UPLOAD_MB} MB).",
            )
        chunks.append(chunk)

    contents = b"".join(chunks)
    if not contents:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")

    result = cv_upload.parse_cv(contents)
    return CVUploadResult.model_validate(result)
