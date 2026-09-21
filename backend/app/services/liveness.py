"""¿Sigue abierta la oferta?

Por que existe
--------------
Las vacantes llegan a la cola y se quedan ahi: una que la empresa cerro hace
dos semanas se ve igual que una publicada hoy, y el swipe, el CV adaptado y
la carta se gastan en ella. career-ops (github.com/career-ops-hq/career-ops,
MIT) comprueba que la oferta siga viva antes de invertir tiempo; esto es lo
mismo, sin navegador.

Como se sabe
------------
  * Greenhouse y Lever tienen una API publica por oferta: 404 = cerrada.
  * Ashby no la tiene por oferta, pero si por tablero: si el tablero responde
    y la oferta ya no esta en el, esta cerrada. El tablero sale de la cache de
    ats_boards, asi que comprobar 20 ofertas de una empresa es una peticion.
  * Cualquier otra pagina: 404/410, o un texto inequivoco de "ya no acepta
    candidaturas". Solo frases completas: una palabra suelta como "closed"
    aparece en cualquier pie de pagina.

"unknown" es una respuesta valida y frecuente: LinkedIn y Jobicy exigen
sesion, Himalayas contesta 403 a todo lo que no es un navegador. Una oferta
que no se pudo comprobar NUNCA se marca como cerrada.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import quote, unquote, urlparse

from app.services.apply_target import _gated_reason
from app.services.job_importer import JobImportError, JobPostingGone, fetch_html_with_url, html_to_text

logger = logging.getLogger(__name__)

Status = Literal["open", "closed", "unknown"]


@dataclass(frozen=True)
class Liveness:
    status: Status
    reason: str = ""


_GREENHOUSE = re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/([\w-]+)/jobs/(\d+)", re.I)
_LEVER = re.compile(r"jobs\.(eu\.)?lever\.co/([\w.-]+)/([0-9a-f]{8}-[0-9a-f-]{27})", re.I)
_ASHBY = re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f]{8}-[0-9a-f-]{27})", re.I)

#: Frases completas, en los dos idiomas. Cada una se vio en paginas reales de
#: ofertas cerradas; ninguna aparece en una oferta abierta.
_CLOSED_TEXT = re.compile(
    r"no longer accepting applications"
    r"|(?:this|the)\s+(?:job|position|role|posting|vacancy|opening)\s+(?:is|has been)\s+"
    r"(?:no longer available|closed|filled|expired|removed|archived)"
    r"|(?:job|posting)\s+(?:has\s+)?expired"
    r"|position\s+has\s+(?:already\s+)?been\s+filled"
    r"|(?:esta|la)\s+(?:vacante|oferta|posici[oó]n)\s+(?:ya\s+no\s+est[aá]\s+disponible|ha\s+sido\s+cerrada|"
    r"ha\s+expirado|est[aá]\s+cerrada)"
    r"|ya\s+no\s+(?:acepta|recibe)\s+(?:postulaciones|candidaturas|solicitudes)",
    re.IGNORECASE,
)


async def _api_status(provider: str, url: str) -> Optional[int]:
    from app.services.external_jobs import http as external_http

    try:
        resp = await external_http.get(provider, url, retries=0)
    except Exception as exc:  # noqa: BLE001 - sin respuesta = no se sabe
        logger.info("liveness %s: %s", url, exc)
        return None
    return resp.status_code


async def _check_greenhouse(slug: str, job_id: str) -> Liveness:
    status = await _api_status("greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}")
    if status == 200:
        return Liveness("open")
    if status == 404:
        return Liveness("closed", "Greenhouse ya no publica esta oferta.")
    return Liveness("unknown", f"Greenhouse respondio {status}.")


async def _check_lever(eu: bool, slug: str, job_id: str) -> Liveness:
    host = "api.eu.lever.co" if eu else "api.lever.co"
    status = await _api_status("lever", f"https://{host}/v0/postings/{slug}/{job_id}")
    if status == 200:
        return Liveness("open")
    if status == 404:
        return Liveness("closed", "Lever ya no publica esta oferta.")
    return Liveness("unknown", f"Lever respondio {status}.")


async def _check_ashby(slug: str, job_id: str) -> Liveness:
    from app.services import ats_boards

    try:
        jobs = await ats_boards._fetch_board("ashby", quote(unquote(slug)))
    except Exception as exc:  # noqa: BLE001
        return Liveness("unknown", f"Ashby no respondio: {exc}")
    if not jobs:
        # Tablero vacio o 404: la empresa pudo cambiar de ATS. No basta.
        return Liveness("unknown", "El tablero de Ashby no devolvio ofertas.")
    if any(str(j.get("id")) == job_id for j in jobs if isinstance(j, dict)):
        return Liveness("open")
    return Liveness("closed", "Ya no esta en el tablero de Ashby de la empresa.")


async def _check_page(url: str) -> Liveness:
    motivo = _gated_reason(url)
    if motivo:
        return Liveness("unknown", motivo)
    try:
        html, final_url = await fetch_html_with_url(url)
    except JobPostingGone as exc:
        return Liveness("closed", str(exc))
    except JobImportError as exc:
        return Liveness("unknown", str(exc))
    if "error=true" in (urlparse(final_url).query or ""):
        # Greenhouse redirige una oferta cerrada al tablero con ?error=true.
        return Liveness("closed", "El ATS redirige al tablero: la oferta ya no existe.")
    m = _CLOSED_TEXT.search(html_to_text(html)[:20000])
    if m:
        return Liveness("closed", f"La pagina dice: “{m.group(0)}”.")
    return Liveness("open")


async def check_liveness(source_url: Optional[str], apply_url: Optional[str] = None) -> Liveness:
    """Una sola comprobacion por oferta; el ATS, si se reconoce, manda."""
    for url in (apply_url, source_url):
        if not url:
            continue
        if m := _GREENHOUSE.search(url):
            return await _check_greenhouse(m.group(1), m.group(2))
        if m := _LEVER.search(url):
            return await _check_lever(bool(m.group(1)), m.group(2), m.group(3))
        if m := _ASHBY.search(url):
            return await _check_ashby(m.group(1), m.group(2))
    # Sin ATS reconocido: la pagina. Si el portal de origen exige sesion, la
    # pagina de la empresa (apply_url) todavia puede contestar.
    for url in (source_url, apply_url):
        if url and not _gated_reason(url):
            return await _check_page(url)
    if source_url:
        return Liveness("unknown", _gated_reason(source_url) or "")
    return Liveness("unknown", "La vacante no tiene URL de origen.")
