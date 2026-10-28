"""Enviar una aplicacion preparada.

Tres canales:

  * email: el correo que el usuario vio en la vista previa. Se vuelve a armar
    desde cero y se compara su huella con la guardada al prepararlo; si algo
    cambio (otro CV, otra carta), no sale: vuelve a "lista" para revisarla.
  * greenhouse: el contenedor `agent` (backend/Dockerfile.agent) abre el
    formulario publico, lo llena con el borrador, adjunta el CV y la carta y
    pulsa enviar. Si aparece un desafio de CAPTCHA, o no se ve la
    confirmacion, NO insiste ni intenta resolverlo: devuelve el control al
    usuario (estado handoff) con el enlace al formulario. Lo mismo si el
    servidor no tiene agente configurado.
  * external: no lo envia JobPilot. Queda en handoff hasta que el usuario
    dice "ya la envie".

Al salir de verdad, la postulacion pasa a "aplicado" con fecha y una nota de
por donde salio: lo que el pipeline y los recordatorios ven.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.models.application import Application
from app.models.application_draft import (
    CHANNEL_EMAIL,
    CHANNEL_GREENHOUSE,
    DRAFT_HANDOFF,
    DRAFT_READY,
    DRAFT_SCHEDULED,
    DRAFT_SUBMITTED,
    DRAFT_SUBMITTING,
    ApplicationDraft,
)
from app.models.career_profile import CareerProfile
from app.models.cover_letter import CoverLetter
from app.models.enums import ApplicationStatus
from app.models.job import Job
from app.models.resume_version import ResumeVersion
from app.models.user import User
from app.services.apply_agent import review
from app.services.apply_agent.notify import notify

logger = logging.getLogger("jobflow.apply")


class SubmitBlocked(RuntimeError):
    """No se puede enviar ahora. El mensaje va tal cual a la interfaz."""


def _store(draft: ApplicationDraft, content: dict[str, Any]) -> None:
    """Guarda el contenido. flag_modified porque a menudo es el MISMO dict que
    ya estaba asignado (y luego se modifico): sin esto SQLAlchemy no ve el
    cambio en una columna JSONB y no lo escribe."""
    draft.content = content
    flag_modified(draft, "content")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _note(content: dict[str, Any], texto: str) -> None:
    content.setdefault("log", []).append({"at": _now().isoformat(), "text": texto})


async def mark_applied(db: AsyncSession, application: Application, nota: str) -> None:
    ahora = _now()
    application.status = ApplicationStatus.applied
    application.applied_at = application.applied_at or ahora
    application.notes = f"{application.notes}\n{nota}" if application.notes else nota


def agent_available() -> bool:
    return bool(settings.APPLY_AGENT_URL)


def _handoff(draft: ApplicationDraft, content: dict[str, Any], motivo: str) -> None:
    draft.status = DRAFT_HANDOFF
    content["handoff_reason"] = motivo
    _note(content, motivo)


async def submit(
    db: AsyncSession, user: User, draft: ApplicationDraft, *, automatic: bool = False, claimed: bool = False
) -> ApplicationDraft:
    """Envia el borrador. `automatic` = lo dispara el reloj (modo auto), no un
    toque del usuario; `claimed` = el reloj ya lo paso a "submitting" bajo
    bloqueo. Lanza SubmitBlocked si no puede ni intentarlo."""
    if draft.status == DRAFT_SUBMITTED:
        return draft
    if draft.status == DRAFT_SUBMITTING and not claimed:
        raise SubmitBlocked("Ya se está enviando.")

    application = (
        await db.execute(select(Application).where(Application.id == draft.application_id))
    ).scalar_one()
    job = (await db.execute(select(Job).where(Job.id == application.job_id))).scalar_one()
    if application.status == ApplicationStatus.applied:
        await _unclaim(db, draft, claimed)
        raise SubmitBlocked("Ya postulaste a esta vacante.")
    if job.closed_at is not None:
        await _unclaim(db, draft, claimed)
        raise SubmitBlocked("La oferta ya está cerrada: no se envía.")

    content = dict(draft.content or {})
    review.refresh(content, draft.channel)
    if review.pending_required(content):
        await _unclaim(db, draft, claimed)
        raise SubmitBlocked("Faltan respuestas obligatorias. Complétalas antes de enviar.")
    if automatic and content.get("review_reasons"):
        # Algo cambio desde que se programo (p. ej. editaron el perfil): un
        # envio automatico solo sale si sigue sin nada que revisar.
        draft.status, draft.scheduled_for = DRAFT_READY, None
        content["auto"] = False
        _note(content, "No salió sola: ahora hay algo que revisar.")
        _store(draft, content)
        await db.commit()
        return draft

    draft.status = DRAFT_SUBMITTING
    _store(draft, content)
    await db.commit()

    try:
        if draft.channel == CHANNEL_EMAIL:
            await _submit_email(db, user, draft, application, job, content)
        elif draft.channel == CHANNEL_GREENHOUSE:
            await _submit_greenhouse(db, user, draft, application, job, content)
        else:
            _handoff(draft, content, "Este destino se envía en la página de la empresa.")
    except SubmitBlocked as exc:
        draft.status = DRAFT_READY
        _note(content, str(exc))
        _store(draft, content)
        await db.commit()
        raise
    except Exception:  # noqa: BLE001 - nunca dejar un borrador en "enviando"
        logger.exception("Fallo al enviar la aplicacion %s", draft.application_id)
        _handoff(draft, content, "Algo falló al enviarla. Envíala tú en la página; nada se marcó como enviado.")

    _store(draft, content)
    await db.commit()
    await db.refresh(draft)
    await _notify_result(db, user, job, draft, automatic)
    return draft


async def _submit_email(db, user, draft, application, job, content) -> None:
    from app.api.v1.routers.applications import _assemble_email_application
    from app.services import apply_by_email

    preview, app_email, *_ = await _assemble_email_application(job.id, user, db)
    if preview.blockers:
        raise SubmitBlocked(preview.blockers[0])
    guardada = (content.get("email") or {}).get("fingerprint")
    if app_email is None or not guardada or preview.fingerprint != guardada:
        content["email"] = preview.model_dump()
        raise SubmitBlocked("El correo cambió desde que lo preparamos. Revísalo otra vez antes de enviar.")
    try:
        await asyncio.to_thread(apply_by_email.send_email_application, app_email)
    except apply_by_email.ApplyEmailError as exc:
        raise SubmitBlocked(str(exc)) from exc
    nota = f"Enviada por correo a {app_email.to} el {_now():%Y-%m-%d %H:%M} UTC."
    _sent(draft, content, nota)
    await mark_applied(db, application, nota)


def _sent(draft: ApplicationDraft, content: dict[str, Any], nota: str) -> None:
    draft.status = DRAFT_SUBMITTED
    draft.submitted_at = _now()
    draft.scheduled_for = None
    _note(content, nota)


async def _pdfs(db: AsyncSession, user: User, draft: ApplicationDraft) -> tuple[Optional[bytes], Optional[bytes]]:
    from app.services.cover_letter_pdf import render_cover_letter_pdf
    from app.services.resume_pdf import render_resume_pdf

    cv = carta = None
    if draft.resume_version_id:
        cv = (await db.execute(select(ResumeVersion).where(ResumeVersion.id == draft.resume_version_id))).scalar_one_or_none()
    if draft.cover_letter_id:
        carta = (await db.execute(select(CoverLetter).where(CoverLetter.id == draft.cover_letter_id))).scalar_one_or_none()
    profile = (await db.execute(select(CareerProfile).where(CareerProfile.user_id == user.id))).scalar_one_or_none()
    contacto = profile.contact_info if profile is not None else {}

    def _render():
        cv_pdf = render_resume_pdf(full_name=user.full_name, contact_info=contacto, content=cv.content,
                                   language=cv.language, email=user.email) if cv is not None else None
        carta_pdf = render_cover_letter_pdf(full_name=user.full_name, contact_info=contacto,
                                            content=carta.content, email=user.email) if carta is not None else None
        return cv_pdf, carta_pdf

    return await asyncio.to_thread(_render)


async def call_agent(payload: dict[str, Any]) -> dict[str, Any]:
    """POST al contenedor agent. Aparte para poder sustituirlo en los tests."""
    async with httpx.AsyncClient(timeout=settings.APPLY_AGENT_TIMEOUT_SECONDS) as client:
        resp = await client.post(settings.APPLY_AGENT_URL.rstrip("/") + "/submit", json=payload)
        resp.raise_for_status()
        return resp.json()


async def _submit_greenhouse(db, user, draft, application, job, content) -> None:
    form_url = draft.form_url or content.get("form_url") or content.get("url")
    if content.get("education_required"):
        _handoff(draft, content, "El formulario pide el bloque de educación, que se llena a mano: envíala en la página.")
        return
    if not agent_available():
        _handoff(draft, content, "El envío desde el servidor no está activo: ábrela en la página y envíala tú "
                                 "(la extensión de JobPilot llena el formulario).")
        return

    cv_pdf, carta_pdf = await _pdfs(db, user, draft)
    if cv_pdf is None:
        raise SubmitBlocked("Falta el CV de esta vacante. Prueba «Rehacer».")
    profile = (await db.execute(select(CareerProfile).where(CareerProfile.user_id == user.id))).scalar_one_or_none()
    pais = ((profile.contact_info or {}).get("country") if profile is not None else "") or ""
    payload = {
        "draft": {"form_url": form_url, "url": content.get("url"), "fields": content.get("fields") or []},
        "country": pais,
        "resume_pdf": base64.b64encode(cv_pdf).decode("ascii"),
        "cover_letter_pdf": base64.b64encode(carta_pdf).decode("ascii") if carta_pdf else None,
    }
    try:
        informe = await call_agent(payload)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Agente no disponible: %s", exc)
        _handoff(draft, content, "El agente de envío no respondió. Envíala tú en la página; nada se marcó como enviado.")
        return

    content["submission"] = {k: v for k, v in informe.items() if k != "screenshot_b64"}
    resultado = informe.get("outcome")
    if resultado == "submitted":
        nota = f"Enviada por el formulario de Greenhouse el {_now():%Y-%m-%d %H:%M} UTC."
        _sent(draft, content, nota)
        await mark_applied(db, application, nota)
    elif resultado == "challenge":
        _handoff(draft, content, "El formulario pidió verificar que eres una persona. JobPilot no toca los "
                                 "CAPTCHA: ábrela y envíala tú, todo lo demás ya está escrito en el borrador.")
    elif resultado == "unconfirmed":
        _handoff(draft, content, "Se pulsó enviar pero no vimos la confirmación. Mira tu correo antes de "
                                 "reenviarla: puede que sí haya llegado.")
    elif resultado == "invalid":
        errores = "; ".join(informe.get("errors") or [])[:300]
        _handoff(draft, content, f"El formulario rechazó algunos campos{': ' + errores if errores else ''}. "
                                 "Corrígelos en la página y envíala tú.")
    else:
        _handoff(draft, content, "No se pudo llenar el formulario en la página. Envíala tú; nada se marcó como enviado.")


async def _unclaim(db: AsyncSession, draft: ApplicationDraft, claimed: bool) -> None:
    """Un programado que el reloj tomo y no puede salir vuelve a "lista"."""
    if claimed:
        draft.status, draft.scheduled_for = DRAFT_READY, None
        await db.commit()


async def mark_sent_by_user(db: AsyncSession, draft: ApplicationDraft) -> ApplicationDraft:
    """El usuario la envio en la pagina de la empresa."""
    application = (
        await db.execute(select(Application).where(Application.id == draft.application_id))
    ).scalar_one()
    content = dict(draft.content or {})
    nota = f"Enviada por ti en la página de la empresa el {_now():%Y-%m-%d %H:%M} UTC."
    _sent(draft, content, nota)
    _store(draft, content)
    await mark_applied(db, application, nota)
    await db.commit()
    await db.refresh(draft)
    return draft


async def _notify_result(db, user, job, draft, automatic: bool) -> None:
    if not automatic:
        return  # el usuario lo esta viendo en la pantalla
    donde = f"{job.title} en {job.company}"
    if draft.status == DRAFT_SUBMITTED:
        cuerpo = f"Enviada: {donde}."
    elif draft.status == DRAFT_HANDOFF:
        cuerpo = f"{donde} necesita que la envíes tú: {(draft.content or {}).get('handoff_reason', '')}"
    else:
        cuerpo = f"{donde} no salió sola: revísala."
    try:
        await notify(db, user.id, "JobPilot", cuerpo[:240], draft.application_id)
    except Exception:  # noqa: BLE001
        logger.exception("Aviso del envio %s", draft.application_id)


# ------------------------------------------------------------------ reloj

async def run_due(db: AsyncSession, limit: int = 5) -> int:
    """Envia los programados cuya hora llego. Devuelve cuantos intento.

    FOR UPDATE SKIP LOCKED + pasar a "submitting" en la misma transaccion:
    aunque un dia corran dos backends, cada borrador sale una vez."""
    filas = (
        await db.execute(
            select(ApplicationDraft)
            .where(ApplicationDraft.status == DRAFT_SCHEDULED, ApplicationDraft.scheduled_for <= _now())
            .order_by(ApplicationDraft.scheduled_for)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()
    for fila in filas:
        fila.status = DRAFT_SUBMITTING
    ids = [f.id for f in filas]
    await db.commit()  # ya son de este reloj: nadie mas los toma

    hechos = 0
    for draft_id in ids:
        draft = (
            await db.execute(select(ApplicationDraft).where(ApplicationDraft.id == draft_id))
        ).scalar_one()
        user = (await db.execute(select(User).where(User.id == draft.user_id))).scalar_one()
        try:
            await submit(db, user, draft, automatic=True, claimed=True)
        except SubmitBlocked as exc:
            logger.info("Programada %s no salió: %s", draft_id, exc)
        except Exception:  # noqa: BLE001
            logger.exception("Programada %s", draft_id)
            await db.rollback()
            # Nunca dejarlo en "enviando": que el usuario lo vea y decida.
            draft = (await db.execute(select(ApplicationDraft).where(ApplicationDraft.id == draft_id))).scalar_one()
            if draft.status == DRAFT_SUBMITTING:
                contenido = dict(draft.content or {})
                _handoff(draft, contenido, "Algo falló al enviarla sola. Revísala; nada se marcó como enviado.")
                _store(draft, contenido)
                await db.commit()
        hechos += 1
    return hechos


async def scheduler_loop(interval_seconds: float = 30.0) -> None:
    """Corre dentro del backend (main.py, al arrancar)."""
    from app.db.session import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_due(db)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - el reloj no se muere por un fallo
            logger.exception("Reloj de envios")
        await asyncio.sleep(interval_seconds)
