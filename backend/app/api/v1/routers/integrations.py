from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_state_token, decode_state_token
from app.db.session import get_db
from app.models.oauth_connection import OAuthConnection
from app.models.user import User
from app.schemas.integration import UpworkAuthorizeResponse, UpworkStatus
from app.services import upwork

router = APIRouter(prefix="/integrations", tags=["integrations"])

_STATE_PURPOSE = "upwork_oauth"


async def _get_upwork_connection(user_id: UUID, db: AsyncSession) -> OAuthConnection | None:
    result = await db.execute(
        select(OAuthConnection).where(OAuthConnection.user_id == user_id, OAuthConnection.provider == "upwork")
    )
    return result.scalar_one_or_none()


@router.get("/upwork/status", response_model=UpworkStatus)
async def upwork_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UpworkStatus:
    connection = await _get_upwork_connection(current_user.id, db)
    return UpworkStatus(connected=connection is not None, configured=upwork.is_configured())


@router.get("/upwork/authorize", response_model=UpworkAuthorizeResponse)
async def upwork_authorize(current_user: User = Depends(get_current_user)) -> UpworkAuthorizeResponse:
    """Returns the Upwork consent-screen URL for the frontend to navigate
    the browser to (`window.location.href = authorization_url`) — it can't
    be a redirect from here since this call carries the user's bearer
    token, which the browser navigation that follows would not."""
    state = create_state_token(current_user.id, purpose=_STATE_PURPOSE)
    try:
        url = upwork.get_authorization_url(state)
    except upwork.UpworkNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return UpworkAuthorizeResponse(authorization_url=url)


@router.get("/upwork/callback")
async def upwork_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Upwork redirects the user's browser here directly after consent —
    there's no Authorization header on this request, so the user identity
    comes from the signed `state` value minted by /upwork/authorize rather
    than a bearer token. Always ends in a redirect back to the frontend's
    import page with a `?upwork=connected|error` flag."""
    frontend_url = settings.FRONTEND_ORIGIN.rstrip("/") + "/jobs/import"

    if error or not code or not state:
        return RedirectResponse(f"{frontend_url}?upwork=error")

    subject = decode_state_token(state, purpose=_STATE_PURPOSE)
    if subject is None:
        return RedirectResponse(f"{frontend_url}?upwork=error")
    try:
        user_id = UUID(subject)
    except ValueError:
        return RedirectResponse(f"{frontend_url}?upwork=error")

    try:
        tokens = await upwork.exchange_code_for_token(code)
    except upwork.UpworkError:
        return RedirectResponse(f"{frontend_url}?upwork=error")

    connection = await _get_upwork_connection(user_id, db)
    if connection is None:
        connection = OAuthConnection(user_id=user_id, provider="upwork", access_token=tokens["access_token"])
        db.add(connection)
    connection.access_token = tokens["access_token"]
    connection.refresh_token = tokens.get("refresh_token")
    connection.token_type = tokens.get("token_type") or "Bearer"
    connection.expires_at = tokens.get("expires_at")
    await db.commit()

    return RedirectResponse(f"{frontend_url}?upwork=connected")


@router.delete("/upwork", status_code=204)
async def upwork_disconnect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    connection = await _get_upwork_connection(current_user.id, db)
    if connection is not None:
        await db.delete(connection)
        await db.commit()
