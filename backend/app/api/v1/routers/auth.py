import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_state_token,
    decode_state_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import (
    ResendVerificationResponse,
    TokenResponse,
    User as UserSchema,
    UserLogin,
    UserRegister,
)
from app.services import email

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("jobflow.auth")

_VERIFY_PURPOSE = "email_verify"
_VERIFY_TOKEN_MINUTES = 10  # short-lived on purpose — request a resend if it expires


def _send_verification_email(user: User) -> None:
    token = create_state_token(user.id, purpose=_VERIFY_PURPOSE, expires_minutes=_VERIFY_TOKEN_MINUTES)
    # Must hit the backend's own GET /auth/verify-email first (it validates
    # the token and flips email_verified), which then redirects on to
    # FRONTEND_ORIGIN/verify-email?status=... — pointing straight at the
    # frontend page here would skip verification entirely, since that page
    # only ever reads `status`, never `token`.
    verification_url = f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}/auth/verify-email?token={token}"
    try:
        email.send_verification_email(user.email, user.full_name, verification_url, _VERIFY_TOKEN_MINUTES)
    except email.EmailError as exc:
        # Never fail registration/login over a flaky mail provider — the user
        # can always request another link via POST /auth/resend-verification.
        logger.warning("Failed to send verification email to %s: %s", user.email, exc)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    existing = await db.execute(select(User).where(User.email == payload.email.lower()))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    _send_verification_email(user)

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserSchema.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserSchema.model_validate(user))


@router.get("/me", response_model=UserSchema)
async def me(current_user: User = Depends(get_current_user)) -> UserSchema:
    return UserSchema.model_validate(current_user)


@router.post("/resend-verification", response_model=ResendVerificationResponse)
async def resend_verification(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ResendVerificationResponse:
    if current_user.email_verified:
        return ResendVerificationResponse(sent=False, detail="Your email is already verified.")
    _send_verification_email(current_user)
    return ResendVerificationResponse(sent=True, detail="Verification email sent.")


@router.get("/verify-email")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    """The link in the verification email points the browser here directly
    (no Authorization header available), so identity comes from the signed
    `token` rather than a bearer token — same pattern as any other
    email/redirect-based confirmation flow. Always ends in a redirect back
    to the frontend with `?status=success|invalid` (an expired token also
    reports as `invalid` — the user just requests a new one either way)."""
    target = f"{settings.FRONTEND_ORIGIN.rstrip('/')}/verify-email"

    subject = decode_state_token(token, purpose=_VERIFY_PURPOSE)
    if subject is None:
        return RedirectResponse(f"{target}?status=invalid")

    try:
        user_id = UUID(subject)
    except ValueError:
        return RedirectResponse(f"{target}?status=invalid")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return RedirectResponse(f"{target}?status=invalid")

    if not user.email_verified:
        user.email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        await db.commit()

    return RedirectResponse(f"{target}?status=success")
