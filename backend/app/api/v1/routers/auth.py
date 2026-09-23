# NOTE: the AI / PDF / SMTP helpers below are synchronous by design, but
# uvicorn runs one event loop: calling one directly from an `async def`
# handler freezes EVERY other request for its whole duration (5-15s for a
# Claude call, up to the SMTP timeout for a slow mail server). They are
# dispatched with asyncio.to_thread so only the calling request waits -
# the same pattern services/match_engine.py already documents.
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.rate_limit import limiter, login_lockout
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_state_token,
    decode_state_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.session import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import (
    RefreshRequest,
    RefreshResponse,
    ResendVerificationResponse,
    TokenResponse,
    User as UserSchema,
    UserLogin,
    UserRegister,
)
from app.services import email

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("jobflow.auth")

# A real bcrypt hash of a value nobody can supply, used only to spend the
# same ~100ms on a login for an address that has no account as on one that
# does. Computed once at import so it never costs anything per request.
_DUMMY_PASSWORD_HASH = hash_password("jobflow-timing-equalizer-not-a-real-password")

_VERIFY_PURPOSE = "email_verify"
_VERIFY_TOKEN_MINUTES = 10  # short-lived on purpose — request a resend if it expires


async def _issue_token_pair(user: User, db: AsyncSession) -> tuple[str, str]:
    """Mints a fresh access token (JWT) + refresh token (opaque, stored
    hashed) for `user`, and commits the refresh token's DB row. Returns
    (access_token, raw_refresh_token) — the raw value is only ever seen by
    the client, never stored."""
    access_token = create_access_token(user.id)
    raw_refresh = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    await db.commit()
    return access_token, raw_refresh


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
@limiter.limit("5/minute")
async def register(request: Request, payload: UserRegister, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    # This 409 tells an anonymous caller whether an address has an account —
    # user enumeration. Kept deliberately, as an accepted risk rather than an
    # oversight:
    #
    #   * the alternative (always answer "check your email") is a genuinely
    #     worse experience for a personal app: typing an address you already
    #     registered would look like success and then silently never log you in;
    #   * the endpoint is rate-limited to 5/minute, so enumerating any real
    #     list of addresses is not practical here;
    #   * with registration open (the default now), the per-IP rate limit is
    #     the only thing standing in the way — accepted for now.
    #
    # Upgrade path if that stops being enough: return 201 either way and send
    # "someone tried to register with your address" to the existing account
    # instead (needs the app to stop auto-logging in after signup). The login path does NOT make
    # the same trade — see the dummy hash there, which removes the timing
    # oracle for an endpoint that is not rate-limited per address.
    # Registro abierto por defecto: cualquiera que instale el APK se crea su
    # cuenta. Los topes globales de api_budget protegen la factura de
    # Anthropic y las cuotas de Adzuna/SerpApi, y GET /system/errors solo le
    # muestra el log completo a la primera cuenta (el operador).
    #
    # ALLOW_EXTRA_REGISTRATIONS=0 en .env lo cierra tras la primera cuenta.
    if not settings.ALLOW_EXTRA_REGISTRATIONS:
        already = await db.execute(select(func.count()).select_from(User))
        if (already.scalar_one() or 0) > 0:
            raise HTTPException(
                status_code=403,
                detail="El registro esta cerrado en esta instalacion.",
            )

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

    await asyncio.to_thread(_send_verification_email, user)

    access_token, refresh_token = await _issue_token_pair(user, db)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user=UserSchema.model_validate(user))


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, payload: UserLogin, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    address = payload.email.lower()
    wait = login_lockout.retry_after(address)
    if wait:
        minutes = -(-wait // 60)
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos fallidos con este correo. Espera {minutes} min y vuelve a intentarlo.",
            headers={"Retry-After": str(wait)},
        )

    result = await db.execute(select(User).where(User.email == address))
    user = result.scalar_one_or_none()
    if user is None:
        # Hash the supplied password against a throwaway value anyway. Short-
        # circuiting on "no such user" skipped bcrypt entirely, so a missing
        # account answered measurably faster than a wrong password — a timing
        # oracle that turns "is this email registered?" into a stopwatch
        # question. Costs one bcrypt round on a path that should be rare.
        await asyncio.to_thread(verify_password, payload.password, _DUMMY_PASSWORD_HASH)
        login_lockout.record_failure(address)
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    # bcrypt is deliberately slow (~100ms+); off the event loop it goes, or
    # every concurrent request waits behind this one.
    if not await asyncio.to_thread(verify_password, payload.password, user.hashed_password):
        login_lockout.record_failure(address)
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    login_lockout.reset(address)

    access_token, refresh_token = await _issue_token_pair(user, db)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user=UserSchema.model_validate(user))


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit("30/minute")
async def refresh(request: Request, payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> RefreshResponse:
    """Exchanges a still-valid refresh token for a new access token — this
    is what actually keeps the user "logged in" across the access token's
    short lifetime, transparently (see frontend/lib/api.ts). Rotates the
    refresh token on every use (the old one is revoked, a new one issued):
    if a stolen refresh token and the real one both later try to use the
    same now-revoked value, that's a signal it leaked, without needing any
    extra infrastructure to detect it."""
    invalid = HTTPException(status_code=401, detail="Invalid or expired refresh token.")

    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()
    if stored is None or stored.expires_at < datetime.now(timezone.utc):
        raise invalid

    if stored.revoked_at is not None:
        # Reuse of an already-rotated token. The docstring above called this
        # "a signal it leaked" but the code only rejected this one token, so
        # the thief — who rotated first and holds the *current* token — kept
        # full access for the rest of the 90-day window while the real user
        # just saw one session drop. Detecting a leak and doing nothing about
        # it is not a security control.
        #
        # Revoking the whole family ends both sessions. Whoever is legitimate
        # logs in again with their password, which the attacker does not have.
        now = datetime.now(timezone.utc)
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == stored.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()
        logger.warning(
            "refresh token reuse detected for user %s — revoked all active sessions",
            stored.user_id,
        )
        raise invalid

    result = await db.execute(select(User).where(User.id == stored.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise invalid

    stored.revoked_at = datetime.now(timezone.utc)
    access_token, new_refresh_token = await _issue_token_pair(user, db)
    return RefreshResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> None:
    """Revokes one refresh token server-side. Best-effort and always 204 —
    logging out doesn't need to prove the token existed, and a client that
    already lost its refresh token has nothing left to revoke anyway (its
    access token still just expires on its own, shortly)."""
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(timezone.utc)
        await db.commit()


@router.get("/me", response_model=UserSchema)
async def me(current_user: User = Depends(get_current_user)) -> UserSchema:
    return UserSchema.model_validate(current_user)


@router.post("/resend-verification", response_model=ResendVerificationResponse)
@limiter.limit("3/minute")
async def resend_verification(
    request: Request, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ResendVerificationResponse:
    if current_user.email_verified:
        return ResendVerificationResponse(sent=False, detail="Your email is already verified.")
    await asyncio.to_thread(_send_verification_email, current_user)
    return ResendVerificationResponse(sent=True, detail="Verification email sent.")


@router.get("/verify-email")
@limiter.limit("20/minute")
async def verify_email(request: Request, token: str, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
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
