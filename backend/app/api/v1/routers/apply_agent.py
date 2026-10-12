"""Endpoints del agente de aplicacion (fase 2: solo borradores).

  POST /applications/{id}/draft  -- prepara (o rehace) el borrador.
  GET  /applications/{id}/draft  -- el ultimo borrador guardado.
  GET  /apply-agent/readiness    -- que le falta al perfil al agente.

Nada de aqui envia una candidatura. Ver tasks/agente-aplicacion.md.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.application import Application
from app.models.application_draft import DRAFT_NEEDS_USER, DRAFT_READY, ApplicationDraft
from app.models.career_profile import CareerProfile
from app.models.user import User
from app.schemas.application_draft import AgentReadiness, ApplicationDraftOut
from app.services.apply_agent.draft import NEEDS_USER, build_draft
from app.services.apply_agent.facts import build_facts, missing_for_agent
from app.services.apply_agent.greenhouse import FormUnavailable, fetch_greenhouse_form, parse_greenhouse_ref

router = APIRouter(tags=["apply-agent"])


async def _profile(db: AsyncSession, user: User) -> Optional[CareerProfile]:
    return (
        await db.execute(select(CareerProfile).where(CareerProfile.user_id == user.id))
    ).scalar_one_or_none()


def _greenhouse_ref(job) -> Optional[tuple[str, str]]:
    """El formulario de Greenhouse de la vacante, si lo es. Se mira primero el
    destino resuelto (apply_url) y luego el listado: las ofertas que entran por
    ats_boards traen el formulario en las dos."""
    for candidato in (job.apply_url, job.source_url):
        ref = parse_greenhouse_ref(candidato)
        if ref:
            return ref
    return None


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


@router.get("/applications/{application_id}/draft", response_model=ApplicationDraftOut)
async def get_draft(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDraft:
    draft = (
        await db.execute(
            select(ApplicationDraft).where(
                ApplicationDraft.application_id == application_id,
                ApplicationDraft.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if draft is None:
        raise HTTPException(status_code=404, detail="Esta postulación todavía no tiene borrador.")
    return draft


@router.post("/applications/{application_id}/draft", response_model=ApplicationDraftOut)
@limiter.limit("30/hour")
async def prepare_draft(
    request: Request,
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDraft:
    application = (
        await db.execute(
            select(Application)
            .options(selectinload(Application.job))
            .where(Application.id == application_id, Application.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if application is None or application.job is None:
        raise HTTPException(status_code=404, detail="No encontramos esa postulación.")

    ref = _greenhouse_ref(application.job)
    if ref is None:
        raise HTTPException(
            status_code=422,
            detail="Por ahora el agente solo prepara formularios de Greenhouse; esta vacante usa otro destino.",
        )

    profile = await _profile(db, current_user)
    if profile is None:
        raise HTTPException(status_code=409, detail="Sube tu CV primero: el agente solo usa datos de tu perfil.")

    try:
        form = await fetch_greenhouse_form(*ref)
    except FormUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    resultado = await build_draft(form, build_facts(current_user, profile))
    contenido = resultado.to_dict()
    falta_usuario = any(f.required and f.status == NEEDS_USER for f in resultado.fields)

    draft = (
        await db.execute(select(ApplicationDraft).where(ApplicationDraft.application_id == application.id))
    ).scalar_one_or_none()
    if draft is None:
        draft = ApplicationDraft(user_id=current_user.id, application_id=application.id)
        db.add(draft)
    draft.ats = form.ats
    draft.form_url = form.form_url
    draft.status = DRAFT_NEEDS_USER if falta_usuario else DRAFT_READY
    draft.auto_eligible = resultado.auto_eligible
    draft.content = contenido
    draft.error = None
    await db.commit()
    await db.refresh(draft)
    return draft
