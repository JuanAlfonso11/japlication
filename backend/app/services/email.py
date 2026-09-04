"""Transactional email — currently just account-verification messages.

Uses plain `smtplib` so it works with any SMTP provider (Gmail app
password, Mailtrap for local dev, SendGrid/Postmark/SES SMTP relay, ...).
When SMTP isn't configured (no `SMTP_HOST`), nothing is sent — the
verification link is written to the backend's own logs instead, so local
development works out of the box without setting up a mail account. This
mirrors the app's established pattern for every other optional external
service (Claude, SerpApi, ...): fully functional offline, better with
credentials.

The logo is embedded inline (Content-ID, not a linked <img src="https://...">)
because the app is normally only reachable over Tailscale — an email client
fetching a linked image would be doing so from its own servers (e.g. Gmail's
image proxy), which can't reach a private VPN address at all. Embedding
sidesteps that entirely.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("jobflow.email")

_LOGO_PATH = Path(__file__).resolve().parent.parent / "data" / "logo_email.png"
_LOGO_CID = "jobpilot-logo"

BRAND_BLUE = "#2547e9"


class EmailError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.SMTP_HOST)


@lru_cache
def _logo_bytes() -> bytes:
    return _LOGO_PATH.read_bytes()


def _send(to_email: str, subject: str, text_body: str, html_body: str, *, with_logo: bool = True) -> None:
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

    if with_logo:
        html_part = message.get_payload()[1]
        html_part.add_related(_logo_bytes(), maintype="image", subtype="png", cid=f"<{_LOGO_CID}>")

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


def _email_shell(inner_html: str) -> str:
    """Google-style shell: light gray backdrop, centered white card, logo
    up top, muted footer with a signature — reused by every email so new
    message types stay visually consistent."""
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:32px 16px;background:#f1f3f4;font-family:'Google Sans',Roboto,Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;margin:0 auto;">
      <tr>
        <td style="text-align:center;padding-bottom:24px;">
          <img src="cid:{_LOGO_CID}" width="56" height="56" alt="JobPilot"
               style="width:56px;height:56px;border-radius:14px;display:inline-block;">
        </td>
      </tr>
      <tr>
        <td style="background:#ffffff;border-radius:16px;padding:40px 32px;
                   box-shadow:0 1px 3px rgba(60,64,67,.15);">
          {inner_html}
        </td>
      </tr>
      <tr>
        <td style="text-align:center;padding-top:24px;color:#5f6368;font-size:12px;line-height:18px;">
          — El equipo de JobPilot<br>
          Este es un mensaje automático, por favor no respondas a este correo.
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def send_verification_email(to_email: str, full_name: str, verification_url: str, expires_minutes: int) -> None:
    first_name = (full_name or "").split(" ")[0] or "there"
    expiry_text = _format_expiry(expires_minutes)
    subject = "Confirma tu cuenta de JobPilot"

    text_body = (
        f"Hola {first_name},\n\n"
        "Gracias por registrarte en JobPilot. Confirma tu correo abriendo este enlace "
        f"(válido por {expiry_text} — si expira, puedes pedir que te enviemos uno nuevo desde la app):"
        f"\n\n{verification_url}\n\n"
        "Si no creaste esta cuenta, puedes ignorar este mensaje.\n\n"
        "— El equipo de JobPilot"
    )

    inner_html = f"""\
      <h1 style="margin:0 0 16px;font-size:22px;font-weight:500;color:#202124;text-align:center;">
        Confirma tu cuenta
      </h1>
      <p style="margin:0 0 24px;font-size:14px;line-height:22px;color:#3c4043;text-align:center;">
        Hola {first_name}, gracias por registrarte en <strong>JobPilot</strong>. Un solo clic y quedas listo
        para empezar a hacer swipe en tus próximas vacantes.
      </p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto 24px;">
        <tr>
          <td style="border-radius:8px;background:{BRAND_BLUE};">
            <a href="{verification_url}"
               style="display:inline-block;padding:12px 32px;font-size:14px;font-weight:600;
                      color:#ffffff;text-decoration:none;border-radius:8px;">
              Verificar mi cuenta
            </a>
          </td>
        </tr>
      </table>
      <p style="margin:0 0 8px;font-size:12px;line-height:18px;color:#80868b;text-align:center;">
        Este enlace vence en {expiry_text}. Si ya venció, puedes pedir uno nuevo desde la app.
      </p>
      <p style="margin:24px 0 0;font-size:12px;line-height:18px;color:#80868b;text-align:center;
                word-break:break-all;">
        ¿El botón no funciona? Copia y pega este enlace en tu navegador:<br>
        <a href="{verification_url}" style="color:{BRAND_BLUE};">{verification_url}</a>
      </p>
      <p style="margin:24px 0 0;font-size:12px;line-height:18px;color:#80868b;text-align:center;">
        Si no creaste esta cuenta, puedes ignorar este mensaje con confianza.
      </p>
    """
    html_body = _email_shell(inner_html)

    _send(to_email, subject, text_body, html_body)
