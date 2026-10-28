"""Aplicar al deslizar: lo que pasa despues de un swipe a la derecha.

Es el flujo /apply de ai-job-search (evaluar -> redactar CV y carta ->
auditar los hechos -> llenar el formulario) hecho servicio, sobre lo que
JobPilot ya tenia:

  1. Puertas (gates.py): elegibilidad, idioma, oferta cerrada o vencida.
  2. CV a medida de la vacante (resume_adapter) -- se reutiliza si ya hay uno
     para ella -- y carta, solo cuando el destino la usa. Si la empresa
     prohibe contenido generado con IA, el CV sale sin IA (las vinetas tal
     cual del perfil) y no se adjunta carta generada.
  3. Auditoria de hechos (grounding.py) del CV y la carta contra el perfil.
  4. El borrador segun por donde sale:
       greenhouse -- el formulario publico, campo por campo (draft.py)
       email      -- la oferta pide enviarla a un correo (apply_by_email.py)
       external   -- cualquier otro sitio (LinkedIn, Workday, la web de la
                     empresa): JobPilot lo deja todo listo y el usuario la
                     envia alli, con la extension llenando el formulario.
  5. Segun el modo del usuario:
       review -- espera su aprobacion (un toque en "Enviar")
       auto   -- si no falta nada y nada pide revision, se programa para
                 dentro de APPLY_UNDO_MINUTES, con tope diario. Se puede
                 deshacer hasta que sale.

Lo que NUNCA hace, en ningun modo: responder un consentimiento, una pregunta
sensible o una legal sin respuesta guardada; inventar un hecho; tocar un
CAPTCHA. Eso lo garantizan draft.py, grounding.py y el agente (filler.py).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.application import Application
from app.models.application_draft import (
    CHANNEL_EMAIL,
    CHANNEL_EXTERNAL,
    CHANNEL_GREENHOUSE,
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
from app.models.cover_letter import CoverLetter
from app.models.enums import GenerationSource
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.resume_version import ResumeVersion
from app.models.user import User
from app.services import work_authorization
from app.services.apply_agent import gates as gates_mod
from app.services.apply_agent import grounding, review
from app.services.apply_agent.draft import FILLED, build_draft
from app.services.apply_agent.facts import build_facts
from app.services.apply_agent.greenhouse import FormUnavailable, fetch_greenhouse_form, parse_greenhouse_ref
from app.services.apply_agent.notify import notify
from app.services.cover_letter_generator import generate_cover_letter
from app.services.profile_i18n import detect_language, localize_profile, normalize_language
from app.services.resume_adapter import _rule_based_adapt, adapt_resume

logger = logging.getLogger("jobflow.apply")

MODE_SAVE = "save"
MODE_REVIEW = "review"
MODE_AUTO = "auto"
APPLY_MODES = (MODE_SAVE, MODE_REVIEW, MODE_AUTO)

#: Un "preparing" mas viejo que esto se considera colgado (reinicio a mitad).
_STALE_PREPARING = timedelta(minutes=5)


def greenhouse_ref(job: Job) -> Optional[tuple[str, str]]:
    """El formulario de Greenhouse de la vacante, si lo es. Primero el destino
    resuelto (apply_url) y luego el listado."""
    for candidato in (job.apply_url, job.source_url):
        ref = parse_greenhouse_ref(candidato)
        if ref:
            return ref
    return None


def channel_for(job: Job) -> str:
    if greenhouse_ref(job):
        return CHANNEL_GREENHOUSE
    if job.apply_email:
        return CHANNEL_EMAIL
    return CHANNEL_EXTERNAL


# ------------------------------------------------------------------ documentos

async def _resume_for(
    db: AsyncSession, user: User, profile: CareerProfile, job: Job, language: str, *, no_ai: bool
) -> ResumeVersion:
    """El CV para esta vacante: el ultimo que ya exista para ella en ese
    idioma (el usuario pudo haberlo editado), o uno nuevo."""
    existente = (
        await db.execute(
            select(ResumeVersion)
            .where(ResumeVersion.user_id == user.id, ResumeVersion.job_id == job.id,
                   ResumeVersion.language == language)
            .order_by(ResumeVersion.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existente is not None:
        return existente

    if no_ai:
        # Sin IA: el adaptador por reglas solo reordena, copia las vinetas tal
        # cual. Es lo unico honesto para una empresa que prohibe la IA.
        resultado = await asyncio.to_thread(_rule_based_adapt, localize_profile(profile, language), job)
        resultado["generated_by"], resultado["language"] = "manual", language
    else:
        resultado = await asyncio.to_thread(adapt_resume, profile, job, language)

    cv = ResumeVersion(
        user_id=user.id,
        career_profile_id=profile.id,
        job_id=job.id,
        title=f"{job.title} @ {job.company}",
        content=resultado["content"],
        change_log=resultado["change_log"],
        language=resultado["language"],
        generated_by=GenerationSource(resultado["generated_by"]),
    )
    db.add(cv)
    await db.flush()
    return cv


async def _cover_letter_for(
    db: AsyncSession, user: User, profile: CareerProfile, job: Job, cv: ResumeVersion
) -> CoverLetter:
    existente = (
        await db.execute(
            select(CoverLetter)
            .where(CoverLetter.user_id == user.id, CoverLetter.job_id == job.id)
            .order_by(CoverLetter.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existente is not None:
        return existente

    match = (
        await db.execute(select(JobMatch).where(JobMatch.user_id == user.id, JobMatch.job_id == job.id))
    ).scalar_one_or_none()
    generada = await asyncio.to_thread(
        generate_cover_letter,
        profile=profile,
        job=job,
        candidate_name=user.full_name,
        matched_skills=list(match.matched_skills) if match else [],
        tone="professional",
    )
    carta = CoverLetter(
        user_id=user.id,
        job_id=job.id,
        resume_version_id=cv.id,
        content=generada["content"],
        tone=generada["tone"],
        generated_by=GenerationSource(generada["generated_by"]),
    )
    db.add(carta)
    await db.flush()
    return carta


def _doc_summary(row: Any, kind: str) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "kind": kind,
        "language": getattr(row, "language", None),
        "generated_by": row.generated_by.value if hasattr(row.generated_by, "value") else row.generated_by,
    }


# ------------------------------------------------------------------ limites

async def auto_sends_today(db: AsyncSession, user_id: UUID) -> int:
    """Envios automaticos de hoy (UTC): los que salieron y los que estan por
    salir. Los aprobados a mano no cuentan."""
    inicio = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    es_auto = ApplicationDraft.content["auto"].as_boolean().is_(True)
    return (
        await db.execute(
            select(func.count()).select_from(ApplicationDraft).where(
                ApplicationDraft.user_id == user_id,
                es_auto,
                or_(
                    ApplicationDraft.status.in_((DRAFT_SCHEDULED, DRAFT_SUBMITTING)),
                    ApplicationDraft.submitted_at >= inicio,
                ),
            )
        )
    ).scalar_one()


# ------------------------------------------------------------------ preparar

async def _upsert(db: AsyncSession, user: User, application: Application) -> ApplicationDraft:
    draft = (
        await db.execute(select(ApplicationDraft).where(ApplicationDraft.application_id == application.id))
    ).scalar_one_or_none()
    if draft is None:
        draft = ApplicationDraft(user_id=user.id, application_id=application.id, ats="", form_url="",
                                 content={})
        db.add(draft)
    return draft


def _base_content(job: Job, channel: str) -> dict[str, Any]:
    return {
        "ats": channel,
        "url": job.apply_url or job.source_url or "",
        "form_url": job.apply_url or job.source_url or "",
        "title": job.title,
        "company": job.company,
        "language": detect_language(job.description),
        "location": job.location or "",
        "ai_policy": False,
        "fields": [],
        "notices": [],
        "education_required": False,
    }


def _attach_documents(content: dict[str, Any], cv: ResumeVersion, carta: Optional[CoverLetter]) -> None:
    """El CV y la carta van en los campos de archivo del formulario."""
    for f in content.get("fields") or []:
        if f.get("type") != "file":
            continue
        etiqueta = (f.get("label") or "").lower()
        if f["key"] == "resume" or "resume" in etiqueta or etiqueta.startswith("cv"):
            f.update(value="tailored_cv", display="Tu CV para esta vacante (PDF)", source="profile",
                     status=FILLED, reason=None)
        elif carta is not None and (f["key"] == "cover_letter" or "cover" in etiqueta or "carta" in etiqueta):
            f.update(value="cover_letter", display="Tu carta para esta vacante (PDF)",
                     source="ai" if _doc_summary(carta, "cover_letter")["generated_by"] == "ai" else "profile",
                     status=FILLED, reason=None)


def _form_wants_cover_letter(form) -> bool:
    return any(
        f.type == "file" and (f.key == "cover_letter" or "cover" in (f.label or "").lower())
        for f in form.fields
    )


async def prepare_application(
    db: AsyncSession, user: User, application: Application, *, mode: Optional[str] = None
) -> ApplicationDraft:
    """Prepara (o rehace) la aplicacion. Nunca lanza por algo de la oferta o
    del perfil: lo deja escrito en el borrador (failed + error) para que la
    app lo enseñe. Si ya salio o esta saliendo, no la toca."""
    mode = mode or user.apply_mode or MODE_REVIEW
    draft = await _upsert(db, user, application)
    if draft.status in (DRAFT_SUBMITTED, DRAFT_SUBMITTING):
        return draft

    job = (await db.execute(select(Job).where(Job.id == application.job_id))).scalar_one()
    channel = channel_for(job)
    draft.status, draft.channel, draft.error = DRAFT_PREPARING, channel, None
    draft.ats = channel
    draft.form_url = job.apply_url or job.source_url or ""
    draft.scheduled_for = None
    await db.commit()

    draft_id, app_id = draft.id, application.id
    try:
        await _prepare(db, user, application, job, draft, mode)
    except Exception:  # noqa: BLE001 - se le dice al usuario, no se cae el swipe
        logger.exception("No se pudo preparar la aplicacion %s", app_id)
        # El rollback caduca todo lo cargado: se vuelve a leer por id, sin
        # tocar atributos caducados (en async eso no se puede cargar solo).
        await db.rollback()
        draft = (
            await db.execute(
                select(ApplicationDraft)
                .where(ApplicationDraft.id == draft_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        draft.status = DRAFT_FAILED
        draft.error = "No se pudo preparar esta aplicación. Prueba «Rehacer» en un rato."
        await db.commit()
        await db.refresh(draft)
        return draft

    await db.commit()
    await db.refresh(draft)
    await _notify_state(db, user, job, draft)
    return draft


async def _prepare(
    db: AsyncSession, user: User, application: Application, job: Job, draft: ApplicationDraft, mode: str
) -> None:
    profile = (
        await db.execute(select(CareerProfile).where(CareerProfile.user_id == user.id))
    ).scalar_one_or_none()
    if profile is None:
        draft.status = DRAFT_FAILED
        draft.error = "Sube tu CV en Perfil: el agente solo aplica con datos de tu perfil."
        draft.content = _base_content(job, draft.channel)
        return

    facts = build_facts(user, profile)
    puertas = gates_mod.evaluate(job, profile, work_authorization.profile_country(profile))
    channel = draft.channel

    form = None
    aviso_canal: Optional[str] = None
    if channel == CHANNEL_GREENHOUSE:
        try:
            form = await fetch_greenhouse_form(*greenhouse_ref(job))
        except FormUnavailable as exc:
            # El formulario no se pudo leer: la vacante sigue, pero sale por la
            # pagina de la empresa como cualquier otra.
            channel = CHANNEL_EXTERNAL if not job.apply_email else CHANNEL_EMAIL
            aviso_canal = str(exc)

    ai_policy = False
    if form is not None:
        from app.services.apply_agent.classify import mentions_ai_policy

        ai_policy = any(mentions_ai_policy(f.label, f.description) for f in form.fields)

    language = normalize_language(form.language if form is not None and form.language else
                                  detect_language(job.description))
    cv = await _resume_for(db, user, profile, job, language, no_ai=ai_policy)
    if cv.edited_at is None:
        cv_content, informe = grounding.audit_resume(cv.content, profile)
        if informe.fixed:
            cv.content = cv_content
    else:
        # Un CV que el usuario corrigio a mano dice lo que el decidio decir.
        informe = grounding.GroundingReport()

    quiere_carta = (
        channel == CHANNEL_EMAIL
        or job.requires_cover_letter
        or (form is not None and _form_wants_cover_letter(form))
    )
    carta = None
    if quiere_carta and not ai_policy:
        carta = await _cover_letter_for(db, user, profile, job, cv)
        grounding.audit_cover_letter(carta.content, profile, informe, job_text=job.description)

    if form is not None:
        borrador = await build_draft(form, facts)
        content = borrador.to_dict()
    else:
        content = _base_content(job, channel)

    _attach_documents(content, cv, carta)
    content["gates"] = [p.to_dict() for p in puertas]
    content["grounding"] = informe.to_dict()
    content["documents"] = {
        "resume": _doc_summary(cv, "resume"),
        "cover_letter": _doc_summary(carta, "cover_letter") if carta is not None else None,
    }
    if aviso_canal:
        content["channel_notice"] = aviso_canal

    if channel == CHANNEL_EMAIL:
        content["email"] = await _email_preview(db, user, job)

    draft.channel = draft.ats = channel
    if form is not None:
        draft.form_url = form.form_url
    application.resume_version_id = cv.id
    if carta is not None:
        application.cover_letter_id = carta.id
    draft.resume_version_id = cv.id
    draft.cover_letter_id = carta.id if carta is not None else None

    auto_ok, _ = review.refresh(content, channel)
    content["auto"] = False
    draft.auto_eligible = auto_ok
    estado, hora = await _next_status(db, user, draft, content, channel, mode, auto_ok)
    draft.content = content  # despues: _next_status anota "auto" en el contenido
    draft.status, draft.scheduled_for = estado, hora


async def _email_preview(db: AsyncSession, user: User, job: Job) -> dict[str, Any]:
    from app.api.v1.routers.applications import _assemble_email_application

    await db.flush()  # el CV y la carta recien creados tienen que verse
    preview, *_ = await _assemble_email_application(job.id, user, db)
    return preview.model_dump()


async def _next_status(
    db: AsyncSession, user: User, draft: ApplicationDraft, content: dict[str, Any],
    channel: str, mode: str, auto_ok: bool,
) -> tuple[str, Optional[datetime]]:
    if channel == CHANNEL_EXTERNAL:
        return DRAFT_HANDOFF, None
    if channel == CHANNEL_EMAIL and (content.get("email") or {}).get("blockers"):
        return DRAFT_NEEDS_USER, None
    if review.pending_required(content):
        return DRAFT_NEEDS_USER, None
    if mode == MODE_AUTO and auto_ok:
        if await auto_sends_today(db, user.id) < settings.APPLY_DAILY_AUTO_LIMIT:
            content["auto"] = True
            return DRAFT_SCHEDULED, datetime.now(timezone.utc) + timedelta(minutes=settings.APPLY_UNDO_MINUTES)
        content["auto_limit_reached"] = True
    return DRAFT_READY, None


async def _notify_state(db: AsyncSession, user: User, job: Job, draft: ApplicationDraft) -> None:
    donde = f"{job.title} en {job.company}"
    if draft.status == DRAFT_SCHEDULED:
        cuerpo = f"Se envía sola en {settings.APPLY_UNDO_MINUTES} min: {donde}. Toca para revisarla o deshacerla."
    elif draft.status == DRAFT_NEEDS_USER:
        n = len((draft.content or {}).get("pending_required") or []) or 1
        cuerpo = f"Te falta{'n' if n != 1 else ''} {n} respuesta{'s' if n != 1 else ''} para aplicar a {donde}."
    elif draft.status == DRAFT_READY:
        cuerpo = f"Lista para enviar: {donde}."
    elif draft.status == DRAFT_HANDOFF:
        cuerpo = f"Tu CV y tus respuestas para {donde} están listos: envíala en la página de la empresa."
    else:
        return
    try:
        await notify(db, user.id, "JobPilot", cuerpo, draft.application_id)
    except Exception:  # noqa: BLE001
        logger.exception("Aviso de la aplicacion %s", draft.application_id)


def is_stale_preparing(draft: ApplicationDraft) -> bool:
    if draft.status != DRAFT_PREPARING or draft.updated_at is None:
        return False
    return datetime.now(timezone.utc) - draft.updated_at > _STALE_PREPARING


async def prepare_in_background(user_id: UUID, application_id: UUID) -> None:
    """Lo que encola el swipe. Su propia sesion: la del request ya se cerro."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        application = (
            await db.execute(select(Application).where(Application.id == application_id))
        ).scalar_one_or_none()
        if user is None or application is None:
            return
        existente = (
            await db.execute(select(ApplicationDraft).where(ApplicationDraft.application_id == application_id))
        ).scalar_one_or_none()
        if existente is not None and existente.status == DRAFT_PREPARING and not is_stale_preparing(existente):
            return  # otro swipe (widget + app) ya la esta preparando
        if existente is not None and existente.status in (DRAFT_SUBMITTED, DRAFT_SUBMITTING, DRAFT_SCHEDULED):
            return
        await prepare_application(db, user, application)
