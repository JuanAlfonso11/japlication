"""El widget "Próxima vacante" de Android: pasar, guardar y deshacer desde la
pantalla de inicio, sin abrir la app.

Por qué una credencial propia y no la sesión normal: la sesión vive en el
WebView y caduca cada 30 minutos; el widget es un proceso aparte que puede
pasar horas sin que la app se abra. Darle el refresh token haría que el
widget y la app se lo rotaran el uno al otro (y cerrar sesión). Así que el
widget recibe un token que solo abre este router:

- POST   /widget/token     (sesión normal) -> emite la credencial del teléfono
- DELETE /widget/token     (credencial)    -> la revoca (cerrar sesión)
- GET    /widget/summary   (credencial)    -> lo que enseña el widget
- POST   /widget/decision  (credencial)    -> el mismo swipe que Home
- POST   /widget/undo      (credencial)    -> el mismo "Deshacer" que Home

Las decisiones llaman a las MISMAS funciones que los endpoints de la app
(swipe_decision, undo_application, list_match_queue): no hay una segunda
lógica de swipe que pueda divergir. Ver app/models/widget_token.py.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.routers.applications import swipe_decision, undo_application
from app.api.v1.routers.match import list_match_queue
from app.core.rate_limit import limiter
from app.core.security import create_refresh_token, hash_refresh_token
from app.db.session import get_db
from app.models.application import Application
from app.models.enums import ApplicationStatus, SwipeDecision
from app.models.user import User
from app.models.widget_token import WidgetToken
from app.schemas.application import DecisionRequest
from app.services.anthropic_client import current_ai_user

router = APIRouter(prefix="/widget", tags=["widget"])

WIDGET_TOKEN_HEADER = "X-Widget-Token"
PAYLOAD_VERSION = 1
#: La tarjeta de arriba más las que van detrás. El widget avanza a la
#: siguiente al instante, sin esperar a la red; con cinco de reserva se
#: pueden encadenar varios toques seguidos.
UPCOMING = 5
MAX_TEXT = 140
_DEVICE_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_PIPELINE = (ApplicationStatus.applied, ApplicationStatus.interviewing, ApplicationStatus.offer)
_REMOTE_LABELS = {"remote": "Remoto", "hybrid": "Híbrido", "onsite": "Presencial"}


# ------------------------------------------------------------------ schemas


class WidgetTokenRequest(BaseModel):
    device_id: str = Field(..., description="UUID que genera el teléfono una sola vez.")

    @field_validator("device_id")
    @classmethod
    def _shape(cls, value: str) -> str:
        if not _DEVICE_ID.match(value):
            raise ValueError("device_id no válido.")
        return value


class WidgetTokenResponse(BaseModel):
    token: str


class WidgetDecisionRequest(BaseModel):
    job_id: UUID
    decision: SwipeDecision


class WidgetUndoRequest(BaseModel):
    application_id: UUID


# ------------------------------------------------------------------ payload


def _clip(text: Optional[str]) -> str:
    clean = " ".join((text or "").split())
    return clean if len(clean) <= MAX_TEXT else clean[: MAX_TEXT - 1] + "…"


def describe_place(location: Optional[str], remote_type: Optional[str]) -> str:
    """Igual que describePlace() en frontend/lib/widgets.ts."""
    mode = _REMOTE_LABELS.get(remote_type or "")
    loc = _clip(location)
    if mode == "Remoto":
        return f"Remoto · {loc}" if loc and "remot" not in loc.lower() else "Remoto"
    if mode and loc:
        return f"{mode} · {loc}"
    return mode or loc


def _job_payload(job: Any) -> dict[str, Any]:
    score = job.match.overall_score if getattr(job, "match", None) is not None else None
    return {
        "id": str(job.id),
        "title": _clip(job.title) or "Vacante",
        "company": _clip(job.company),
        "place": describe_place(job.location, job.remote_type),
        "score": None if score is None else max(0, min(100, round(score))),
    }


async def build_summary(user: User, db: AsyncSession) -> dict[str, Any]:
    """La misma forma que WidgetPayload en frontend/lib/widgets.ts, para que
    el teléfono la guarde tal cual venga de aquí o de la app."""
    queue = await list_match_queue(min_score=None, limit=UPCOMING + 1, offset=0, current_user=user, db=db)
    jobs = [_job_payload(j) for j in queue.items]

    rows = (
        await db.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.user_id == user.id, Application.status.in_(_PIPELINE))
            .group_by(Application.status)
        )
    ).all()
    counts = {s.value: n for s, n in rows}

    return {
        "v": PAYLOAD_VERSION,
        "updatedAt": int(time.time() * 1000),
        "queueCount": queue.total,
        "next": jobs[0] if jobs else None,
        "upcoming": jobs[1:],
        "pipeline": {
            "applied": counts.get("applied", 0),
            "interviewing": counts.get("interviewing", 0),
            "offer": counts.get("offer", 0),
        },
    }


# ------------------------------------------------------------------ auth


async def get_widget_token(
    x_widget_token: Optional[str] = Header(None, alias=WIDGET_TOKEN_HEADER),
    db: AsyncSession = Depends(get_db),
) -> WidgetToken:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="El widget se desconectó. Abre JobPilot para volver a conectarlo.",
    )
    if not x_widget_token or len(x_widget_token) > 200:
        raise unauthorized
    row = (
        await db.execute(
            select(WidgetToken).where(
                WidgetToken.token_hash == hash_refresh_token(x_widget_token),
                WidgetToken.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise unauthorized
    row.last_used_at = datetime.now(timezone.utc)
    return row


async def get_widget_user(
    token: WidgetToken = Depends(get_widget_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = (await db.execute(select(User).where(User.id == token.user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cuenta no encontrada.")
    current_ai_user.set(str(user.id))
    return user


# ------------------------------------------------------------------ routes


@router.post("/token", response_model=WidgetTokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def issue_widget_token(
    request: Request,
    payload: WidgetTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WidgetTokenResponse:
    now = datetime.now(timezone.utc)
    # Un teléfono, una credencial: la anterior de ese teléfono deja de
    # valer, sea de esta cuenta o de otra que usó el mismo teléfono.
    await db.execute(
        update(WidgetToken)
        .where(WidgetToken.device_id == payload.device_id, WidgetToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    raw = create_refresh_token()
    db.add(WidgetToken(user_id=current_user.id, device_id=payload.device_id, token_hash=hash_refresh_token(raw)))
    await db.commit()
    return WidgetTokenResponse(token=raw)


@router.delete("/token", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_widget_token(
    token: WidgetToken = Depends(get_widget_token),
    db: AsyncSession = Depends(get_db),
) -> None:
    token.revoked_at = datetime.now(timezone.utc)
    await db.commit()


@router.get("/summary")
async def widget_summary(
    user: User = Depends(get_widget_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    summary = await build_summary(user, db)
    await db.commit()  # last_used_at
    return summary


@router.post("/decision")
async def widget_decision(
    payload: WidgetDecisionRequest,
    user: User = Depends(get_widget_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    application = await swipe_decision(
        job_id=payload.job_id,
        payload=DecisionRequest(decision=payload.decision),
        current_user=user,
        db=db,
    )
    return {"application_id": str(application.id), "summary": await build_summary(user, db)}


@router.post("/undo")
async def widget_undo(
    payload: WidgetUndoRequest,
    user: User = Depends(get_widget_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await undo_application(application_id=payload.application_id, current_user=user, db=db)
    return {"summary": await build_summary(user, db)}
