from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.career_profile import CareerProfile
from app.models.user import User
from app.schemas.career_profile import CareerProfile as CareerProfileSchema
from app.schemas.career_profile import CareerProfileUpsert, CVUploadResult
from app.schemas.cv_evaluation import CVEvaluation
from app.services import cv_upload
from app.services.cv_evaluator import evaluate_cv

router = APIRouter(prefix="/profile", tags=["profile"])


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

    if profile is None:
        profile = CareerProfile(user_id=current_user.id, **data)
        db.add(profile)
    else:
        for field, value in data.items():
            setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)
    return CareerProfileSchema.model_validate(profile)


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
async def import_cv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> CVUploadResult:
    """Parse an uploaded PDF resume into a draft CareerProfile. Nothing is
    persisted here — the frontend pre-fills the profile editor with the
    result and the user still has to review it and hit Save."""
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=422, detail="Please upload a PDF file.")

    max_bytes = settings.MAX_CV_UPLOAD_MB * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(status_code=413, detail=f"PDF is too large (max {settings.MAX_CV_UPLOAD_MB} MB).")
    if not contents:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")

    result = cv_upload.parse_cv(contents)
    return CVUploadResult.model_validate(result)
