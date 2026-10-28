"""Endpoints del agente de aplicacion.

  GET  /apply-agent/settings                   -- que hace el swipe a la derecha
  PUT  /apply-agent/settings                   -- cambiarlo (save | review | auto)
  GET  /apply-agent/readiness                  -- que le falta al perfil al agente
  GET  /apply-agent/drafts                     -- la bandeja de aplicaciones en curso
  POST /applications/{id}/draft                -- prepara (o rehace) la aplicacion
  GET  /applications/{id}/draft                -- el borrador guardado
  PATCH /applications/{id}/draft/answers       -- respuestas del usuario
  POST /applications/{id}/draft/submit         -- enviar ya (la aprobacion del usuario)
  POST /applications/{id}/draft/cancel         -- descartar / deshacer un envio programado
  POST /applications/{id}/draft/mark-sent      -- "ya la envie en la pagina"

El swipe a la derecha (routers/applications.py) encola la preparacion; esto es
lo que la app usa despues. Ver services/apply_agent/pipeline.py y submit.py.
"""

from __future__ import annotations

import copy
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.application import Application
from app.models.application_draft import (
    DRAFT_CANCELLED,
    DRAFT_FAILED,
    DRAFT_HANDOFF,
    DRAFT_NEEDS_USER,
    DRAFT_PREPARING,
    DRAFT_READY,
    DRAFT_SCHEDULED,
    DRAFT_SUBMITTED,
    DRAFT_SUBMITTING,
    ApplicationDraft,
)
from app.models.career_profile import CareerProfile
from app.models.job import Job
from app.models.user import User
from app.schemas.application import JobSummary
from app.schemas.application_draft import (
    AgentReadiness,
    ApplicationDraftListItem,
    ApplicationDraftOut,
    ApplySettings,
    ApplySettingsUpdate,
    DraftAnswers,
)
from app.services.apply_agent import pipeline, review, submit as submit_mod
from app.services.apply_agent.facts import build_facts, missing_for_agent

router = APIRouter(tags=["apply-agent"])

#: Lo que la bandeja ensena por defecto: lo que aun pide algo o esta por salir.
ACTIVE_STATUSES = (
    DRAFT_PREPARING, DRAFT_NEEDS_USER, DRAFT_READY, DRAFT_SCHEDULED, DRAFT_SUBMITTING, DRAFT_HANDOFF, DRAFT_FAILED,
)


async def _profile(db: AsyncSession, user: User) -> Optional[CareerProfile]:
    return (
        await db.execute(select(CareerProfile).where(CareerProfile.user_id == user.id))
    ).scalar_one_or_none()


async def _application(db: AsyncSession, user: User, application_id: UUID) -> Application:
    application = (
        await db.execute(
            select(Application).where(Application.id == application_id, Application.user_id == user.id)
        )
    ).scalar_one_or_none()
    if application is None:
        raise HTTPException(status_code=404, detail="No encontramos esa postulación.")
    return application


async def _draft(db: AsyncSession, user: User, application_id: UUID) -> ApplicationDraft:
    draft = (
        await db.execute(
            select(ApplicationDraft).where(
                ApplicationDraft.application_id == application_id,
                ApplicationDraft.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if draft is None:
        raise HTTPException(status_code=404, detail="Esta postulación todavía no tiene borrador.")
    return draft


# ------------------------------------------------------------------ ajustes

@router.get("/apply-agent/settings", response_model=ApplySettings)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplySettings:
    return ApplySettings(
        apply_mode=current_user.apply_mode or pipeline.MODE_REVIEW,
        daily_auto_limit=settings.APPLY_DAILY_AUTO_LIMIT,
        undo_minutes=settings.APPLY_UNDO_MINUTES,
        agent_available=submit_mod.agent_available(),
        auto_sent_today=await pipeline.auto_sends_today(db, current_user.id),
    )


@router.put("/apply-agent/settings", response_model=ApplySettings)
async def update_settings(
    payload: ApplySettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplySettings:
    current_user.apply_mode = payload.apply_mode
    await db.commit()
    return await get_settings(current_user=current_user, db=db)


@router.get("/apply-agent/readiness", response_model=AgentReadiness)
async def agent_readiness(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentReadiness:
    profile = await _profile(db, current_user)
    if profile is None:
        return AgentReadiness(ready=False, missing=["perfil (sube tu CV)"])
    faltan = missing_for_agent(build_facts(current_user, profile))
    return AgentReadiness(ready=not faltan, missing=faltan)


# ------------------------------------------------------------------ bandeja

@router.get("/apply-agent/drafts", response_model=list[ApplicationDraftListItem])
async def list_drafts(
    active: bool = Query(True, description="Solo lo que aun pide algo o esta por salir."),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApplicationDraftListItem]:
    consulta = (
        select(ApplicationDraft, Application.job_id, Job)
        .join(Application, Application.id == ApplicationDraft.application_id)
        .join(Job, Job.id == Application.job_id)
        .where(ApplicationDraft.user_id == current_user.id)
        .order_by(ApplicationDraft.updated_at.desc())
        .limit(limit)
    )
    if active:
        consulta = consulta.where(ApplicationDraft.status.in_(ACTIVE_STATUSES))
    filas = (await db.execute(consulta)).all()
    salida = []
    for draft, job_id, job in filas:
        contenido = draft.content or {}
        salida.append(
            ApplicationDraftListItem(
                id=draft.id,
                application_id=draft.application_id,
                job_id=job_id,
                status=draft.status,
                channel=draft.channel,
                auto_eligible=draft.auto_eligible,
                error=draft.error,
                pending_count=len(contenido.get("pending_required") or []),
                review_reason_texts=list(contenido.get("review_reason_texts") or []),
                handoff_reason=contenido.get("handoff_reason"),
                scheduled_for=draft.scheduled_for,
                submitted_at=draft.submitted_at,
                updated_at=draft.updated_at,
                job=JobSummary.model_validate(job),
            )
        )
    return salida


# ------------------------------------------------------------------ un borrador

@router.get("/applications/{application_id}/draft", response_model=ApplicationDraftOut)
async def get_draft(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDraft:
    return await _draft(db, current_user, application_id)


@router.post("/applications/{application_id}/draft", response_model=ApplicationDraftOut)
@limiter.limit("30/hour")
async def prepare_draft(
    request: Request,
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDraft:
    """Prepara o rehace la aplicacion ahora mismo (sin esperar al swipe).
    Nunca la envia: en modo automatico la deja programada, como el swipe."""
    application = await _application(db, current_user, application_id)
    if await _profile(db, current_user) is None:
        raise HTTPException(status_code=409, detail="Sube tu CV primero: el agente solo usa datos de tu perfil.")
    existente = (
        await db.execute(select(ApplicationDraft).where(ApplicationDraft.application_id == application.id))
    ).scalar_one_or_none()
    if existente is not None and existente.status in (DRAFT_SUBMITTED, DRAFT_SUBMITTING):
        raise HTTPException(status_code=409, detail="Esta aplicación ya salió: no se rehace.")
    return await pipeline.prepare_application(db, current_user, application)


@router.patch("/applications/{application_id}/draft/answers", response_model=ApplicationDraftOut)
async def answer_draft(
    application_id: UUID,
    payload: DraftAnswers,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDraft:
    draft = await _draft(db, current_user, application_id)
    if draft.status in (DRAFT_SUBMITTED, DRAFT_SUBMITTING, DRAFT_PREPARING):
        raise HTTPException(status_code=409, detail="Ahora mismo no se puede cambiar esta aplicación.")
    contenido = copy.deepcopy(draft.content or {})
    try:
        review.apply_answers(contenido, payload.answers)
    except review.AnswerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.cover_letter_reviewed is not None:
        carta = (contenido.get("documents") or {}).get("cover_letter")
        if carta:
            carta["reviewed"] = payload.cover_letter_reviewed
    auto_ok, _ = review.refresh(contenido, draft.channel)
    draft.auto_eligible = auto_ok
    draft.content = contenido
    flag_modified(draft, "content")
    if draft.status in (DRAFT_NEEDS_USER, DRAFT_READY):
        draft.status = DRAFT_NEEDS_USER if review.pending_required(contenido) else DRAFT_READY
    elif draft.status == DRAFT_SCHEDULED and review.pending_required(contenido):
        # Borro una respuesta obligatoria de algo que iba a salir solo: ya no sale.
        draft.status, draft.scheduled_for = DRAFT_NEEDS_USER, None
    await db.commit()
    await db.refresh(draft)
    return draft


@router.post("/applications/{application_id}/draft/submit", response_model=ApplicationDraftOut)
@limiter.limit("30/hour")
async def submit_draft(
    request: Request,
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDraft:
    """El toque en "Enviar": la aprobacion del usuario para ESTA aplicacion."""
    draft = await _draft(db, current_user, application_id)
    if draft.status in (DRAFT_PREPARING, DRAFT_FAILED, DRAFT_CANCELLED):
        raise HTTPException(status_code=409, detail="Esta aplicación no está lista para enviarse.")
    try:
        return await submit_mod.submit(db, current_user, draft)
    except submit_mod.SubmitBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/applications/{application_id}/draft/cancel", response_model=ApplicationDraftOut)
async def cancel_draft(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDraft:
    """Descarta la aplicacion (o deshace un envio automatico que aun no salio).
    La vacante sigue guardada en el pipeline."""
    draft = await _draft(db, current_user, application_id)
    if draft.status in (DRAFT_SUBMITTED, DRAFT_SUBMITTING):
        raise HTTPException(status_code=409, detail="Ya salió: no se puede deshacer.")
    draft.status, draft.scheduled_for = DRAFT_CANCELLED, None
    contenido = copy.deepcopy(draft.content or {})
    contenido["auto"] = False
    draft.content = contenido
    flag_modified(draft, "content")
    await db.commit()
    await db.refresh(draft)
    return draft


@router.post("/applications/{application_id}/draft/mark-sent", response_model=ApplicationDraftOut)
async def mark_sent(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDraft:
    """El usuario la envio en la pagina de la empresa."""
    draft = await _draft(db, current_user, application_id)
    if draft.status == DRAFT_SUBMITTED:
        return draft
    if draft.status == DRAFT_SUBMITTING:
        raise HTTPException(status_code=409, detail="Se está enviando ahora mismo.")
    return await submit_mod.mark_sent_by_user(db, draft)
