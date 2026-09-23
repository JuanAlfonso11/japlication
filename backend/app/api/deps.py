from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise credentials_exception

    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise credentials_exception

    try:
        user_id = UUID(subject)
    except ValueError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def is_operator(user: User, db: AsyncSession) -> bool:
    """The operator (admin) is the first account ever created — the person
    running this install. Everyone who registered after is a regular user."""
    first_id = (await db.execute(select(User.id).order_by(User.created_at).limit(1))).scalar_one_or_none()
    return user.id == first_id


async def require_operator(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not await is_operator(current_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el administrador puede ver esto.")
    return current_user
