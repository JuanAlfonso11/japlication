"""Postular por correo: la unica via de envio directo que existe.

Por que solo el correo
----------------------
Verificado dos veces, la ultima contra ai-job-search del 21-09-2026: ese
proyecto no envia nada por diseño ("drafts only, never sends"), y los ATS
que si tienen endpoint de envio -- Greenhouse, Lever -- exigen la clave de API
del EMPLEADOR (ver apply_target.py). LinkedIn e Indeed prohiben automatizar
el envio y lo hacen cumplir cerrando la cuenta.

Queda una via legitima: la vacante que dice "envia tu CV a talento@empresa".
Ahi postular ES mandar un correo, y JobPilot puede mandarlo desde la cuenta
del usuario. Todo lo demas se queda como estaba: guardado en el pipeline,
con el formulario resuelto a un toque, para postular a mano.

Las reglas que no se negocian
-----------------------------
Esto manda un correo con el nombre del usuario a un empleador real, y un
correo enviado no se puede retirar. Por eso:

  * Nunca desde el barrido ni en segundo plano. Solo cuando el usuario toca
    "Enviar" sobre una vista previa concreta.

  * Lo que se envia es EXACTAMENTE lo que se previsualizo. La vista previa
    devuelve una huella (sha256 de destinatario, asunto, cuerpo y adjuntos) y
    el envio la exige. Si algo cambio entre medias -- el CV se regenero, la
    carta se edito -- se rechaza y hay que mirar otra vez.

  * Una vez por vacante. Si ya consta como postulada, no se reenvia: dos
    correos iguales al mismo reclutador restan, no suman.

  * Si el SMTP no esta configurado, ERROR, no silencio. email._send registra
    en el log y vuelve como si nada cuando falta SMTP_HOST -- correcto para un
    enlace de verificacion en desarrollo, desastroso aqui: el usuario creeria
    haber postulado y la candidatura no habria salido nunca.

  * El CV tiene que pasar el chequeo ATS. Es el mismo PDF que va adjunto, y
    si una maquina no lo puede leer no tiene sentido mandarlo.

  * Sale DE la cuenta del usuario y responde A su correo. El remitente de los
    correos de verificacion es SMTP_FROM_EMAIL, que por defecto es un
    no-reply: una candidatura enviada asi llega sin forma de contestar.
"""

from __future__ import annotations

import hashlib
import logging
import re
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger("jobflow.apply_email")


class ApplyEmailError(RuntimeError):
    """Algo impide enviar. El mensaje es para el usuario."""


@dataclass
class Attachment:
    filename: str
    content: bytes
    maintype: str = "application"
    subtype: str = "pdf"
    #: Lo que determina el contenido, para la huella. Por defecto, los propios
    #: bytes. Para un PDF hay que pasar su ORIGEN: reportlab mete la fecha de
    #: creacion y un /ID aleatorio en cada render, asi que dos renders del mismo
    #: CV dan bytes distintos. Con la huella sobre los bytes, el envio se
    #: rechazaba SIEMPRE por "el correo cambio desde la vista previa" -- el test
    #: del camino feliz lo cazo.
    source: Optional[bytes] = None


@dataclass
class EmailApplication:
    to: str
    reply_to: str
    subject: str
    body: str
    attachments: list[Attachment] = field(default_factory=list)

    def fingerprint(self) -> str:
        """Huella de todo lo que se va a enviar.

        Incluye el contenido de los adjuntos, no solo su nombre: un CV
        regenerado se llama igual y dice otra cosa.
        """
        h = hashlib.sha256()
        for parte in (self.to, self.reply_to, self.subject, self.body):
            h.update(parte.encode("utf-8"))
            h.update(b"\x00")
        for adj in self.attachments:
            h.update(adj.filename.encode("utf-8"))
            h.update(hashlib.sha256(adj.source if adj.source is not None else adj.content).digest())
        return h.hexdigest()


def is_configured() -> bool:
    """Hace falta un SMTP y una cuenta autenticada: sin cuenta no hay
    remitente real, y sin remitente real la candidatura no es del usuario."""
    return bool(settings.SMTP_HOST and settings.SMTP_USER)


def _safe_filename(text: str) -> str:
    limpio = re.sub(r"[^\w\s.-]", "", text, flags=re.UNICODE).strip()
    limpio = re.sub(r"\s+", "_", limpio)
    return limpio[:60] or "documento"


def build_email_application(
    *,
    to: str,
    reply_to: str,
    full_name: str,
    job_title: str,
    company: str,
    cover_letter_text: Optional[str],
    resume_pdf: bytes,
    cover_letter_pdf: Optional[bytes],
    language: str = "es",
    resume_source: Optional[bytes] = None,
    cover_letter_source: Optional[bytes] = None,
) -> EmailApplication:
    """Arma el correo. No envia nada."""
    if language == "en":
        subject = f"Application: {job_title} — {full_name}"
        saludo_fallback = (
            f"Dear {company} hiring team,\n\n"
            f"Please find attached my CV for the {job_title} position.\n\n"
            f"Best regards,\n{full_name}"
        )
    else:
        subject = f"Candidatura: {job_title} — {full_name}"
        saludo_fallback = (
            f"Estimado equipo de {company}:\n\n"
            f"Adjunto mi CV para la posición de {job_title}.\n\n"
            f"Saludos cordiales,\n{full_name}"
        )

    # La carta ya esta escrita para esta vacante: es el cuerpo natural del
    # correo. Se adjunta ademas en PDF porque muchos reclutadores la reenvian
    # tal cual a quien decide, y el cuerpo de un correo no sobrevive a eso.
    body = (cover_letter_text or "").strip() or saludo_fallback

    base = _safe_filename(full_name)
    adjuntos = [Attachment(f"CV_{base}.pdf", resume_pdf, source=resume_source)]
    if cover_letter_pdf:
        nombre_carta = "Cover_Letter" if language == "en" else "Carta"
        adjuntos.append(
            Attachment(f"{nombre_carta}_{base}.pdf", cover_letter_pdf, source=cover_letter_source)
        )

    return EmailApplication(
        to=to, reply_to=reply_to, subject=subject, body=body, attachments=adjuntos
    )


def send_email_application(app: EmailApplication) -> None:
    """Envia. Lanza ApplyEmailError si no sale -- nunca vuelve en silencio."""
    if not is_configured():
        raise ApplyEmailError(
            "El correo no está configurado (falta SMTP_HOST o SMTP_USER en .env). "
            "No se envió nada."
        )

    message = EmailMessage()
    message["Subject"] = app.subject
    # De la cuenta autenticada, no de SMTP_FROM_EMAIL: ese es el remitente de
    # los correos de verificacion y por defecto es un no-reply. Gmail ademas
    # reescribe el From a la cuenta autenticada, asi que otro valor no llegaria
    # igual.
    message["From"] = settings.SMTP_USER
    message["To"] = app.to
    message["Reply-To"] = app.reply_to
    message.set_content(app.body)
    for adj in app.attachments:
        message.add_attachment(
            adj.content, maintype=adj.maintype, subtype=adj.subtype, filename=adj.filename
        )

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            rechazados: dict[str, Any] = server.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise ApplyEmailError(f"No se pudo enviar el correo: {exc}") from exc

    # send_message devuelve los destinatarios que el servidor rechazo sin
    # lanzar. Con un solo destinatario, que aparezca ahi es que no salio.
    if rechazados:
        raise ApplyEmailError(f"El servidor rechazó el destinatario: {app.to}")

    logger.info("candidatura enviada por correo a %s (%s)", app.to, app.subject)
