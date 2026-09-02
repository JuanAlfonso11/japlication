from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.career_profile import CareerProfile
from app.models.user import User
from app.schemas.career_profile import CareerProfile as CareerProfileSchema
from app.schemas.career_profile import CareerProfileUpsert

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
