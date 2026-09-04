from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.device_token import DeviceToken
from app.models.user import User
from app.schemas.device_token import DeviceTokenRegister

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/register-device", status_code=status.HTTP_204_NO_CONTENT)
async def register_device(
    payload: DeviceTokenRegister,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Saves (or reassigns) an FCM device token for the current user. A
    token is globally unique — re-registering it (e.g. app reinstall, or a
    different account logging in on the same device) just repoints it at
    whoever owns it now rather than erroring."""
    stmt = (
        pg_insert(DeviceToken)
        .values(user_id=current_user.id, token=payload.token, platform=payload.platform)
        .on_conflict_do_update(
            index_elements=[DeviceToken.token],
            set_={"user_id": current_user.id, "platform": payload.platform, "updated_at": func.now()},
        )
    )
    await db.execute(stmt)
    await db.commit()


@router.delete("/register-device", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device(
    payload: DeviceTokenRegister,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Removes a device token — call on logout so a signed-out device stops
    receiving another account's notifications."""
    result = await db.execute(
        select(DeviceToken).where(DeviceToken.token == payload.token, DeviceToken.user_id == current_user.id)
    )
    token_row = result.scalar_one_or_none()
    if token_row is not None:
        await db.delete(token_row)
        await db.commit()
