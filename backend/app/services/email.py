"""Transactional email — currently just account-verification messages.

Uses plain `smtplib` so it works with any SMTP provider (Gmail app
password, Mailtrap for local dev, SendGrid/Postmark/SES SMTP relay, ...).
When SMTP isn't configured (no `SMTP_HOST`), nothing is sent — the
verification link is written to the backend's own logs instead, so local
development works out of the box without setting up a mail account. This
mirrors the app's established pattern for every other optional external
service (Claude, SerpApi, ...): fully functional offline, better with
credentials.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("jobflow.email")


class EmailError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.SMTP_HOST)


def _send(to_email: str, subject: str, text_body: str, html_body: str) -> None:
    if not is_configured():
        logger.warning(
            "SMTP is not configured (SMTP_HOST unset) — not sending a real email. "
            "Message that would have been sent to %s:\n%s",
            to_email,
            text_body,
        )
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to_email
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailError(f"Could not send email via SMTP: {exc}") from exc


def _format_expiry(expires_minutes: int) -> str:
    if expires_minutes % 60 == 0 and expires_minutes >= 60:
        hours = expires_minutes // 60
        return f"{hours} hora" + ("s" if hours != 1 else "")
    return f"{expires_minutes} minuto" + ("s" if expires_minutes != 1 else "")


def send_verification_email(to_email: str, full_name: str, verification_url: str, expires_minutes: int) -> None:
    first_name = (full_name or "").split(" ")[0] or "there"
    expiry_text = _format_expiry(expires_minutes)
    subject = "Confirma tu cuenta de JobFlow AI"
    text_body = (
        f"Hola {first_name},\n\n"
        "Gracias por registrarte en JobFlow AI. Confirma tu correo haciendo clic en este enlace "
        f"(válido por {expiry_text} — si expira, puedes pedir que te enviemos uno nuevo desde la app):"
        f"\n\n{verification_url}\n\n"
        "Si no creaste esta cuenta, puedes ignorar este mensaje.\n"
    )
    html_body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;">
      <h2>Confirma tu cuenta</h2>
      <p>Hola {first_name},</p>
      <p>Gracias por registrarte en JobFlow AI. Confirma tu correo con el siguiente botón
         (el enlace es válido por {expiry_text} — si expira, puedes pedir que te enviemos uno nuevo
         desde la app):</p>
      <p>
        <a href="{verification_url}"
           style="display:inline-block;background:#2b5d63;color:#fff;padding:10px 20px;
                  border-radius:8px;text-decoration:none;font-weight:600;">
          Verificar mi cuenta
        </a>
      </p>
      <p style="color:#666;font-size:13px;">Si el botón no funciona, copia y pega este enlace:<br>
         <a href="{verification_url}">{verification_url}</a></p>
      <p style="color:#999;font-size:12px;">Si no creaste esta cuenta, puedes ignorar este mensaje.</p>
    </div>
    """
    _send(to_email, subject, text_body, html_body)
