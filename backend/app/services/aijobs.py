"""Artificial Intelligence Jobs (artificialintelligencejobs.co) -- empleos de IA
sacados de las paginas de empleo de cada empresa. Gratis, sin clave.
Docs: https://artificialintelligencejobs.co/developers

Lo que la hace distinta de las demas:

* **No trae descripcion.** Cada resultado es solo titulo, empresa, ubicacion,
  categoria, nivel, salario en texto, fecha y dos URLs. La descripcion se
  arma con esos datos para que la tarjeta y el match tengan algo, y dice
  claramente que el detalle esta en la oferta.
* **`apply_url` es el ATS de la empresa** (Greenhouse, Workable, Ashby...),
  asi que se entrega resuelto como en ats_boards.py.
* **Sin id.** La URL de la ficha termina en un slug con hash
  (`.../jobs/empresa-titulo-93106b8e`) que es estable; ese slug es el id.
* **Salario como texto** (`"$162K - $180K  Offers Equity"`, `"CA$115K"`):
  se interpreta solo cuando el formato es inequivoco; si no, queda vacio en
  vez de inventar un numero.
* **Nivel**: `Entry | Mid | Senior | Lead+`, tambien como filtro del servidor.

Piden atribucion (enlace a artificialintelligencejobs.co): `source_url` es
siempre su ficha, y la etiqueta de la fuente en Discover lleva su nombre.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.services import experience_level
from app.services.apply_target import detect_ats
from app.services.external_jobs import http as external_http
from app.services.job_importer import parse_job_text_heuristic

ENDPOINT = "https://artificialintelligencejobs.co/api/jobs"
PAGE_SIZE = 100  # su maximo es 200; 100 deja margen para el filtro local
_CACHE_TTL_SECONDS = 15 * 60
_search_cache: dict[str, dict[str, Any]] = {}

_LEVEL_FROM_NATIVE = {
    "intern": "internship",
    "internship": "internship",
    "entry": "entry",
    "mid": "mid",
    "senior": "senior",
    "lead+": "lead",
    "lead": "lead",
}
_LEVEL_TO_NATIVE = {"entry": "Entry", "mid": "Mid", "senior": "Senior", "lead": "Lead+"}

_CURRENCIES = {"$": "USD", "US$": "USD", "CA$": "CAD", "A$": "AUD", "£": "GBP", "€": "EUR"}
_AMOUNT = re.compile(r"(CA\$|US\$|A\$|\$|£|€)\s?(\d+(?:\.\d+)?)\s?([Kk])?")


class AIJobsError(RuntimeError):
    pass


def parse_salary(text: Optional[str]) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """`"$162K - $180K  Offers Equity"` -> (162000, 180000, "USD").

    Devuelve (None, None, None) ante cualquier duda: monedas mezcladas, mas de
    dos cifras, o cantidades sin "K" por debajo de 1000 (casi siempre son
    tarifas por hora, y guardarlas como sueldo anual seria peor que nada).
    """
    if not text:
        return None, None, None
    found = _AMOUNT.findall(text)
    if not found or len(found) > 2 or len({sym for sym, _, _ in found}) != 1:
        return None, None, None
    amounts = []
    for _, number, k in found:
        value = float(number) * (1000 if k else 1)
        if value < 1000:
            return None, None, None
        amounts.append(value)
    currency = _CURRENCIES.get(found[0][0])
    return amounts[0], amounts[-1], currency


def _job_id(url: Optional[str]) -> Optional[str]:
    path = urlparse(url or "").path.rstrip("/")
    slug = path.rsplit("/", 1)[-1] if path else ""
    return slug or None


def _remote_type(raw: dict[str, Any]) -> str:
    if raw.get("remote"):
        return "remote"
    if "hybrid" in str(raw.get("location") or "").lower():
        return "hybrid"
    return "onsite"


def _parse_posted(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _description(raw: dict[str, Any]) -> str:
    parts = [f"{raw.get('title') or 'Position'} at {raw.get('company') or 'the company'}."]
    for label, key in (("Location", "location"), ("Category", "category"), ("Level", "level"), ("Salary", "salary")):
        if raw.get(key):
            parts.append(f"{label}: {str(raw[key]).strip()}.")
    parts.append("This source lists roles without the full description; open the posting for the details.")
    return " ".join(parts)


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    title = raw.get("title") or "Untitled position"
    company = raw.get("company") or "Unknown company"
    description = _description(raw)
    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    native = str(raw.get("level") or "").strip().lower()
    level = _LEVEL_FROM_NATIVE.get(native) or experience_level.infer(title)

    salary_min, salary_max, currency = parse_salary(raw.get("salary"))
    apply_url = raw.get("apply_url") or None

    return {
        "aijobs_job_id": _job_id(raw.get("url")),
        "source": "aijobs",
        "source_url": raw.get("url") or apply_url,
        "apply_url": apply_url,
        "apply_ats": detect_ats(apply_url),
        "title": title,
        "company": company,
        "location": raw.get("location") or None,
        "remote_type": _remote_type(raw),
        "employment_type": parsed["employment_type"],
        "seniority": level,
        "description": description,
        "requirements": [],
        "responsibilities": [],
        "skills_required": parsed["skills_required"],
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": currency,
        "posted_at": _parse_posted(raw.get("posted")),
    }


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def search_aijobs_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
    page: Optional[int] = None,
) -> dict[str, Any]:
    """`location` se aplica aqui y no en el servidor: sus filtros `city` y
    `region` usan su propio vocabulario ("US", "Asia-Pacific"...), mientras
    que Discover manda nombres de pais. Con remoto pedido no se filtra por
    ubicacion: en una vacante remota es la sede, no donde se puede vivir."""
    params: dict[str, Any] = {"limit": PAGE_SIZE}
    if q:
        params["q"] = q
    if remote_type_filter == "remote":
        params["remote"] = "true"
    native_level = _LEVEL_TO_NATIVE.get(experience_level_filter or "")
    if native_level:
        params["level"] = native_level
    offset = ((page or 1) - 1) * PAGE_SIZE
    if offset:
        params["offset"] = offset

    try:
        resp = await external_http.get("aijobs", ENDPOINT, params=params)
    except httpx.HTTPError as exc:
        raise AIJobsError("Could not reach Artificial Intelligence Jobs (network error).") from exc

    if resp.status_code != 200:
        raise AIJobsError(f"Artificial Intelligence Jobs request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise AIJobsError("Artificial Intelligence Jobs returned a non-JSON response.") from exc

    loc = (location or "").strip().lower()
    filter_location = bool(loc) and remote_type_filter != "remote" and loc not in ("remote", "remoto", "worldwide")

    now = time.time()
    raw_jobs = data.get("jobs") or []
    results = []
    for raw in raw_jobs:
        normalized = _normalize(raw)
        if remote_type_filter and normalized["remote_type"] != remote_type_filter:
            continue
        if filter_location and loc not in (normalized["location"] or "").lower():
            continue
        if not experience_level.matches(normalized["seniority"], experience_level_filter):
            continue
        if normalized["aijobs_job_id"]:
            _search_cache[normalized["aijobs_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    matched = data.get("matched")
    has_more = isinstance(matched, int) and offset + len(raw_jobs) < matched
    return {"results": results, "has_more": has_more}


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
