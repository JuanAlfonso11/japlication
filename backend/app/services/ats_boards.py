"""Ofertas leidas directamente del ATS de cada empresa.

Por que existe
--------------
Medido sobre las 252 vacantes guardadas: 172 venian de portales que esconden
el formulario (jobicy exige cuenta, himalayas contesta 403 de Cloudflare,
LinkedIn exige sesion). Ninguna herramienta puede sacar de ahi el destino.

Estas no tienen ese problema por construccion. Greenhouse, Lever y Ashby
publican las ofertas de cada empresa en una API publica de LECTURA, sin clave:

    GET boards-api.greenhouse.io/v1/boards/{empresa}/jobs?content=true
    GET api.lever.co/v0/postings/{empresa}?mode=json
    GET api.ashbyhq.com/posting-api/job-board/{empresa}

Es la misma familia de APIs que investigamos para enviar: leer es publico,
ENVIAR exige la clave del empleador (ver apply_target.py). Asi que cada oferta
que entra por aqui trae el formulario real desde el primer momento.

La idea y la lista semilla de empresas vienen de career-ops
(github.com/career-ops-hq/career-ops, MIT). Cada empresa de app/data/
ats_companies.json se verifico en vivo; 8 de las de career-ops ya daban 404.

Dos decisiones que conviene saber
---------------------------------
  * Solo remotas por defecto (ATS_REMOTE_ONLY). Estos tableros publican TODO
    lo de la empresa -- "Hybrid - London", "Account Executive" -- y el usuario
    busca desde fuera de esas oficinas. "Remote - US" SI pasa, aunque suele
    exigir autorizacion de trabajo en EE. UU.: filtrar eso bien necesita leer
    la descripcion, no la ubicacion.

  * Se filtra ANTES de normalizar. Normalizar corre parse_job_text_heuristic
    (198 regex sobre la descripcion); hacerlo sobre las ~15.000 ofertas de los
    101 tableros seria minutos. Filtrando primero por titulo y modalidad solo
    se normaliza lo que se va a devolver.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import json
import logging
import re
import time
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from app.services.job_importer import html_to_text, parse_job_text_heuristic

logger = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parent.parent / "data" / "ats_companies.json"

_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
}

#: Un tablero cambia poco en media hora, y cada busqueda recorre decenas: sin
#: esta cache cada pull-to-refresh pediria 50 tableros otra vez.
_BOARD_TTL = 30 * 60
_RESULT_TTL = 30 * 60
_CONCURRENCIA = 8
_MAX_RESULTADOS = 60

_boards: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
_results: dict[str, tuple[float, dict[str, Any]]] = {}

#: "Remote", pero tambien como lo escriben de verdad: Canonical pone "Home
#: based - Americas" y la primera version, que solo buscaba "remote", la daba
#: por presencial con 164 ofertas de ingenieria dentro.
_REMOTE_RE = re.compile(
    r"\b(remote|remoto|anywhere|worldwide|home[\s-]?based|distributed|work from home|wfh)\b",
    re.IGNORECASE,
)
_HYBRID_RE = re.compile(r"\b(hybrid|h[ií]brido)\b", re.IGNORECASE)

#: Sin termino de busqueda (Discover sin texto), no se devuelve "todo": se
#: devuelve lo de ingenieria, que es lo que la app busca.
_ENGINEERING_RE = re.compile(
    r"\b(engineer|developer|software|backend|back-end|full[\s-]?stack|frontend|devops|sre|"
    r"platform|programador|desarrollador|ingenier)\w*",
    re.IGNORECASE,
)


class AtsBoardError(RuntimeError):
    """Se lanza solo si TODOS los tableros fallan; uno caido no tumba la busqueda."""


@lru_cache
def companies() -> list[dict[str, str]]:
    return json.loads(_DATA.read_text(encoding="utf-8"))["companies"]


def companies_for(ats: str) -> list[dict[str, str]]:
    return [c for c in companies() if c["ats"] == ats]


# ---------------------------------------------------------------- lectura

async def _fetch_board(ats: str, slug: str) -> list[dict[str, Any]]:
    clave = (ats, slug)
    ahora = time.time()
    guardado = _boards.get(clave)
    if guardado and ahora - guardado[0] < _BOARD_TTL:
        return guardado[1]

    # Import aqui, no arriba: external_jobs.registry importa este modulo, y
    # arriba el ciclo rompia a quien importara ats_boards primero.
    from app.services.external_jobs import http as external_http

    resp = await external_http.get(ats, _URLS[ats].format(slug=slug))
    status = getattr(resp, "status_code", 200)
    if status == 404:
        # La empresa cambio de ATS o de slug. No es un fallo del proveedor:
        # se recuerda como vacio para no volver a pedirlo en media hora.
        _boards[clave] = (ahora, [])
        return []
    if status != 200:
        raise AtsBoardError(f"{ats}/{slug}: HTTP {status}")
    data = resp.json()
    jobs = data.get("jobs") if isinstance(data, dict) else data
    jobs = jobs if isinstance(jobs, list) else []
    _boards[clave] = (ahora, jobs)
    return jobs


# ---------------------------------------------------------------- campos

def _title(ats: str, raw: dict[str, Any]) -> str:
    return (raw.get("text") if ats == "lever" else raw.get("title")) or ""


def _location_text(ats: str, raw: dict[str, Any]) -> str:
    if ats == "greenhouse":
        partes = [(raw.get("location") or {}).get("name")]
        partes += [o.get("name") for o in raw.get("offices") or [] if isinstance(o, dict)]
    elif ats == "lever":
        cat = raw.get("categories") or {}
        partes = [cat.get("location"), *(cat.get("allLocations") or []), raw.get("workplaceType")]
    else:
        partes = [raw.get("location"), raw.get("workplaceType")]
        partes += [s.get("location") for s in raw.get("secondaryLocations") or [] if isinstance(s, dict)]
    return " · ".join(str(p) for p in partes if p)


def _remote_type(ats: str, raw: dict[str, Any], loc: str) -> Optional[str]:
    wt = str(raw.get("workplaceType") or "").lower().replace("_", "-")
    # La modalidad declarada manda: Ashby marca isRemote=True en ofertas
    # "Hybrid" de Londres (medido en vivo), asi que isRemote va despues.
    if wt == "hybrid":
        return "hybrid"
    if wt in ("onsite", "on-site", "in office", "inoffice"):
        return "onsite"
    if wt == "remote" or raw.get("isRemote") is True or _REMOTE_RE.search(loc):
        return "remote"
    if _HYBRID_RE.search(loc):
        return "hybrid"
    return None


def _title_matches(title: str, q: Optional[str]) -> bool:
    if not q:
        return bool(_ENGINEERING_RE.search(title))
    t = title.lower()
    palabras = [w for w in re.split(r"[\s,/|]+", q.lower()) if len(w) > 1]
    # Todas las palabras del termino, como palabra o prefijo: "Software
    # Engineer" encaja con "Senior Software Engineer, Backend".
    return all(re.search(r"\b" + re.escape(w), t) for w in palabras)


def _parse_dt(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):  # lever: milisegundos
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(value: Any) -> Optional[date]:
    dt = _parse_dt(value)
    if dt is None:
        return None
    d = dt.date()
    return d if d >= date.today() else None


def _description(ats: str, raw: dict[str, Any]) -> str:
    if ats == "greenhouse":
        # Greenhouse manda el HTML escapado dos veces: &lt;p&gt;...
        return html_to_text(html_lib.unescape(raw.get("content") or ""))
    if ats == "ashby":
        return (raw.get("descriptionPlain") or html_to_text(raw.get("descriptionHtml") or "")).strip()
    partes = [raw.get("descriptionPlain") or ""]
    for lista in raw.get("lists") or []:
        if isinstance(lista, dict):
            partes.append(f"{lista.get('text') or ''}:\n{html_to_text(lista.get('content') or '')}")
    partes.append(raw.get("additionalPlain") or "")
    return "\n\n".join(p for p in partes if p.strip()).strip()


def _normalize(ats: str, company: dict[str, str], raw: dict[str, Any], loc: str, remote: Optional[str]) -> dict[str, Any]:
    title = _title(ats, raw) or "Untitled position"
    name = raw.get("company_name") or company["name"]
    description = _description(ats, raw) or "No description provided."
    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=name)

    if ats == "greenhouse":
        url = raw.get("absolute_url")
        apply = url  # el formulario de Greenhouse esta en la misma pagina
        posted = _parse_dt(raw.get("first_published") or raw.get("updated_at"))
        deadline = _parse_date(raw.get("application_deadline"))
    elif ats == "lever":
        url = raw.get("hostedUrl")
        apply = raw.get("applyUrl") or url
        posted = _parse_dt(raw.get("createdAt"))
        deadline = None
    else:
        url = raw.get("jobUrl")
        apply = raw.get("applyUrl") or url
        posted = _parse_dt(raw.get("publishedAt"))
        deadline = None

    return {
        "ats_job_id": f"{ats}:{company['slug']}:{raw.get('id')}",
        "source": ats,
        "source_url": url,
        "apply_url": apply,
        "apply_ats": ats,
        "title": title,
        "company": name,
        "location": loc or None,
        "remote_type": remote or parsed.get("remote_type"),
        "employment_type": parsed.get("employment_type"),
        "seniority": parsed.get("seniority"),
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"],
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "posted_at": posted,
        "deadline": deadline,
    }


# ---------------------------------------------------------------- busqueda

async def search_ats_jobs(
    ats: str,
    q: Optional[str] = None,
    location: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
) -> dict[str, Any]:
    empresas = companies_for(ats)
    sem = asyncio.Semaphore(_CONCURRENCIA)
    fallos = 0

    async def uno(company):
        nonlocal fallos
        async with sem:
            try:
                return company, await _fetch_board(ats, company["slug"])
            except Exception as exc:  # noqa: BLE001 - un tablero caido no tumba a los demas
                fallos += 1
                logger.info("ats %s/%s: %s", ats, company["slug"], exc)
                return company, []

    tableros = await asyncio.gather(*[uno(c) for c in empresas])
    if empresas and fallos == len(empresas):
        raise AtsBoardError(f"Ningun tablero de {ats} respondio.")

    loc_q = (location or "").strip().lower()
    candidatos: list[tuple[dict, dict, str, Optional[str]]] = []
    for company, jobs in tableros:
        for raw in jobs:
            if raw.get("isListed") is False:
                continue
            if not _title_matches(_title(ats, raw), q):
                continue
            loc = _location_text(ats, raw)
            remote = _remote_type(ats, raw, loc)
            if remote_type_filter:
                if remote != remote_type_filter:
                    continue
            elif settings.ATS_REMOTE_ONLY and remote != "remote":
                continue
            if loc_q and loc_q not in loc.lower() and not re.search(r"anywhere|worldwide", loc, re.I):
                continue
            candidatos.append((company, raw, loc, remote))

    # Lo mas reciente primero, y solo entonces normalizar: ver la cabecera.
    def _fecha(item):
        _, raw, _, _ = item
        d = _parse_dt(raw.get("first_published") or raw.get("updated_at") or raw.get("publishedAt") or raw.get("createdAt"))
        return d or datetime.min.replace(tzinfo=timezone.utc)

    candidatos.sort(key=_fecha, reverse=True)
    elegidos = candidatos[:_MAX_RESULTADOS]

    ahora = time.time()
    resultados = []
    for company, raw, loc, remote in elegidos:
        job = _normalize(ats, company, raw, loc, remote)
        _results[job["ats_job_id"]] = (ahora, job)
        resultados.append(job)
    return {"results": resultados, "has_more": len(candidatos) > len(elegidos)}


def get_cached_result(ats_job_id: str) -> Optional[dict[str, Any]]:
    entry = _results.get(ats_job_id)
    if entry is None:
        return None
    if time.time() - entry[0] > _RESULT_TTL:
        _results.pop(ats_job_id, None)
        return None
    return entry[1]
