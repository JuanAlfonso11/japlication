"""Donde se postula de verdad a una vacante.

El problema, medido sobre las 252 vacantes guardadas: NINGUNA URL apunta al
formulario. Todas apuntan al listado del portal -- remotejobs.org, jobicy.com,
himalayas.app, linkedin -- y el formulario real esta siempre un salto mas
alla, en el ATS de la empresa. Eso significa que por cada vacante hay que
abrir el listado, buscar el boton de postular, y seguirlo. Doscientas
cincuenta y dos veces, a mano.

Este modulo hace ese salto una vez y lo guarda.

Sobre enviar la candidatura automaticamente
-------------------------------------------
No se puede, y conviene dejar escrito por que para no volver a investigarlo.
Los endpoints de envio EXISTEN en los ATS grandes, pero son para la empresa
que recibe, no para quien postula:

  * Greenhouse, POST /v1/boards/{board_token}/jobs/{id}: "the Basic Auth
    username is your API key (found on the API Credentials page)" -- esa clave
    esta en la cuenta del empleador.
  * Lever, POST /v0/postings/{site}/{id}?key=APIKEY: la clave la genera un
    "Super Admin" del empleador desde sus ajustes de integraciones.

Sirven para que una empresa monte su propia pagina de empleo. No hay version
para el candidato. Queda automatizar el navegador sobre LinkedIn o Indeed, que
sus terminos prohiben y hacen cumplir cerrando cuentas -- precisamente la
cuenta con la que se esta buscando trabajo.

Asi que lo que se automatiza es todo lo demas: encontrar el formulario,
preparar cada respuesta, y enviar por correo donde la vacante da una
direccion. El ultimo clic lo da la persona, que ademas es quien tiene que
haber leido lo que firma.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.services.job_importer import JobImportError, fetch_html_with_url
from app.services.url_guard import validate_public_http_url

logger = logging.getLogger(__name__)

#: host -> nombre del ATS. Saber cual es determina que campos pide el
#: formulario, que es lo que permite preparar las respuestas de antemano.
_ATS_HOSTS: dict[str, str] = {
    "boards.greenhouse.io": "greenhouse",
    "job-boards.greenhouse.io": "greenhouse",
    "greenhouse.io": "greenhouse",
    "jobs.lever.co": "lever",
    "lever.co": "lever",
    "jobs.ashbyhq.com": "ashby",
    "ashbyhq.com": "ashby",
    "apply.workable.com": "workable",
    "workable.com": "workable",
    "jobs.smartrecruiters.com": "smartrecruiters",
    "smartrecruiters.com": "smartrecruiters",
    "myworkdayjobs.com": "workday",
    "recruitee.com": "recruitee",
    "teamtailor.com": "teamtailor",
    "breezy.hr": "breezy",
    "jobs.jobvite.com": "jobvite",
    "icims.com": "icims",
    "bamboohr.com": "bamboohr",
    "rippling.com": "rippling",
    "pinpointhq.com": "pinpoint",
    "join.com": "join",
    "personio.de": "personio",
    "workforcenow.adp.com": "adp",
}

#: Portales de anuncios. Aterrizar aqui NO es haber encontrado el formulario:
#: es seguir en un listado, y hay que buscar el enlace de postular dentro.
_BOARD_HOSTS = {
    "remotejobs.org", "jobicy.com", "himalayas.app", "remotive.com",
    "arbeitnow.com", "weworkremotely.com", "workingnomads.com",
    "remoteok.com", "remoteok.io", "getonbrd.com", "themuse.com",
    "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
    "news.ycombinator.com", "usajobs.gov", "adzuna.com", "web3.career",
}

#: El texto de un boton de postular, en los dos idiomas.
#:
#: Las formas en espanol van como raiz + \w*, no como palabra cerrada. La
#: primera version ponia `postul` entre \b...\b, que exige frontera de palabra
#: justo despues -- asi que "Postular", que es como lo escribe casi todo el
#: mundo, NO coincidia. El test lo cazo. Mismo error de raiz que el del "plus"
#: en job_importer: una frontera de palabra puesta donde hacia falta un
#: prefijo, y al reves.
_APPLY_TEXT = re.compile(
    r"\b(apply|application|postul\w*|aplic\w*|solicit\w*|inscrib\w*|"
    r"candidatura)\b",
    re.IGNORECASE,
)

#: Portales que NO publican el destino: exigen cuenta antes de enseñarlo.
#: Comprobado, no supuesto -- en jobicy el boton "Apply Now" pasa por su
#: propio registro, y su API v2 (`/api/v2/remote-jobs`) no trae ningun campo
#: con la URL del empleador: solo `url`, que es su propia pagina.
#:
#: Se distinguen de "no se encontro el enlace" a proposito. Son cosas
#: distintas: una es un hueco que se puede mejorar, la otra es un muro. Si
#: ambas dijeran lo mismo, se perderia tiempo intentando arreglar lo segundo.
_GATED_BOARDS: dict[str, str] = {
    "jobicy.com": "Jobicy exige crear cuenta antes de enseñar el formulario; su API tampoco lo trae.",
    "linkedin.com": "LinkedIn exige sesión iniciada para ver el destino de la candidatura.",
    "indeed.com": "Indeed exige sesión iniciada para ver el destino de la candidatura.",
    "glassdoor.com": "Glassdoor exige sesión iniciada para ver el destino de la candidatura.",
}


def _gated_reason(url: str) -> Optional[str]:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for board, motivo in _GATED_BOARDS.items():
        if host == board or host.endswith("." + board):
            return motivo
    return None


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

#: Buzones genericos que aparecen en un pie de pagina y no son para postular.
_EMAIL_NOISE = re.compile(
    r"^(no-?reply|privacy|legal|support|help|info|sales|marketing|press|"
    r"security|abuse|dpo|gdpr|webmaster|contact)@",
    re.IGNORECASE,
)


@dataclass
class ApplyTarget:
    #: La URL del formulario real, si se encontro.
    url: Optional[str] = None
    #: Que ATS es, cuando se reconoce. None = no reconocido (no = no hay).
    ats: Optional[str] = None
    #: Direccion a la que la vacante pide enviar la candidatura, si la publica.
    email: Optional[str] = None
    #: Por que no se pudo resolver. Se guarda para poder mejorarlo despues en
    #: vez de mirar una columna vacia sin saber si fallo o si no habia nada.
    note: Optional[str] = None


def detect_ats(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower().lstrip(".")
    if host.startswith("www."):
        host = host[4:]
    for known, name in _ATS_HOSTS.items():
        if host == known or host.endswith("." + known):
            return name
    return None


def _is_board(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return any(host == b or host.endswith("." + b) for b in _BOARD_HOSTS)


def apply_email_in_text(text: str) -> Optional[str]:
    """La direccion a la que la oferta pide escribir, si publica una.

    Se exige un marcador ("envia tu CV a", "apply by email to") cerca: una
    oferta menciona correos que no son para postular -- el de privacidad, el
    de soporte -- y mandar la candidatura al buzon equivocado es peor que no
    mandarla, porque parece enviada y no llega a nadie.
    """
    if not text:
        return None
    lowered = text.lower()
    marcadores = (
        "envia tu cv", "envía tu cv", "enviar tu cv", "enviar cv",
        "envianos tu cv", "envíanos tu cv", "postula enviando",
        "manda tu cv", "hoja de vida a", "curriculum a", "currículum a",
        "send your cv", "send your resume", "send cv", "send resume",
        "apply by email", "email your", "applications to", "resumes to",
        "cv to", "apply to",
    )
    for marcador in marcadores:
        idx = lowered.find(marcador)
        if idx == -1:
            continue
        ventana = text[idx : idx + 200]
        for match in _EMAIL_RE.finditer(ventana):
            correo = match.group(0)
            if not _EMAIL_NOISE.match(correo):
                return correo
    return None


def _candidate_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Enlaces de la pagina que podrian ser el boton de postular, en orden de
    confianza: primero los que ya apuntan a un ATS conocido."""
    ats_links: list[str] = []
    text_links: list[str] = []

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        absolute = urljoin(base_url, href)
        if not absolute.lower().startswith(("http://", "https://")):
            continue

        if detect_ats(absolute):
            ats_links.append(absolute)
            continue

        etiqueta = " ".join(
            filter(None, [anchor.get_text(" ", strip=True), anchor.get("title") or "",
                          " ".join(anchor.get("class") or []), anchor.get("id") or ""])
        )
        if _APPLY_TEXT.search(etiqueta) and not _is_board(absolute):
            text_links.append(absolute)

    # Sin duplicados y conservando el orden: el primero es el mas probable.
    vistos: set[str] = set()
    ordenados: list[str] = []
    for link in ats_links + text_links:
        if link not in vistos:
            vistos.add(link)
            ordenados.append(link)
    return ordenados


async def resolve_apply_target(listing_url: str, description: str = "") -> ApplyTarget:
    """Sigue el listado hasta el formulario. Nunca lanza: no encontrarlo es un
    resultado normal, no un fallo."""
    correo = apply_email_in_text(description)

    try:
        validate_public_http_url(listing_url)
    except Exception:
        return ApplyTarget(email=correo, note="La URL guardada no es utilizable.")

    gated = _gated_reason(listing_url)
    if gated:
        # Ni se pide la pagina: se sabe de antemano que no trae el destino, y
        # pedirla igual seria una peticion a un tercero a cambio de nada.
        return ApplyTarget(email=correo, note=gated)

    try:
        html, final_url = await fetch_html_with_url(listing_url)
    except JobImportError as exc:
        # Cloudflare y compañia contestan 403 con una pagina de desafio.
        # Comprobado en himalayas.app: status 403, cuerpo "Just a moment...".
        # Eso no se arregla con un User-Agent -- el proyecto ya manda uno de
        # navegador -- asi que se nombra en vez de dejarlo como error generico.
        if "himalayas.app" in listing_url or "403" in str(exc):
            return ApplyTarget(
                email=correo,
                note="El portal bloquea las peticiones automáticas (desafío anti-bot).",
            )
        return ApplyTarget(email=correo, note=f"No se pudo abrir el listado: {exc}")
    except Exception as exc:  # noqa: BLE001 - resolver nunca puede tumbar al que llama
        logger.warning("apply_target: fallo al abrir %s", listing_url, exc_info=exc)
        return ApplyTarget(email=correo, note="No se pudo abrir el listado.")

    # Puede que la redireccion ya haya aterrizado en el ATS.
    ats = detect_ats(final_url)
    if ats:
        return ApplyTarget(url=final_url, ats=ats, email=correo)

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:  # noqa: BLE001
        return ApplyTarget(email=correo, note="No se pudo leer el listado.")

    # El correo de la propia pagina manda sobre el de la descripcion guardada,
    # que puede venir recortada por el portal.
    correo = apply_email_in_text(soup.get_text(" ", strip=True)) or correo

    for candidato in _candidate_links(soup, final_url):
        try:
            validate_public_http_url(candidato)
        except Exception:
            continue
        ats = detect_ats(candidato)
        if ats:
            return ApplyTarget(url=candidato, ats=ats, email=correo)
        # Un enlace de postular que no es un ATS conocido sigue siendo el
        # formulario: casi siempre es la pagina de empleo de la propia
        # empresa. Vale mas que quedarse en el listado.
        return ApplyTarget(url=candidato, ats=None, email=correo)

    if correo:
        return ApplyTarget(email=correo, note="Sin formulario; la oferta pide postular por correo.")

    gated = _gated_reason(final_url) or _gated_reason(listing_url)
    if gated:
        return ApplyTarget(note=gated)
    return ApplyTarget(note="No se encontro el enlace de postular en el listado.")
