"""freehire (freehire.me) -- agregador de empleos de IT, gratis y sin clave.
Docs: https://freehire.me/docs/api (proyecto MIT: github.com/strelov1/freehire)

Es la misma fuente que la skill /freehire de ai-job-search, aqui como una
fuente mas del barrido y de Buscar.

Lo que la hace distinta:

* **`url` es la oferta original** (el ATS de la empresa o la bolsa de origen),
  no una pagina de freehire. Va como `source_url` y `apply_url`, con el ATS
  ya detectado, igual que aidevboard.
* **Nivel con vocabulario propio** (`intern|junior|middle|senior|lead|staff|
  principal|c_level`). Casi ninguna oferta lo trae, asi que el filtro va con
  `seniority_include_unspecified=true`: sin eso `junior` deja fuera la
  mayoria del catalogo.
* **`reality=fresh`**: freehire marca las ofertas viejas o "eternas" (las que
  la bolsa republica para que parezcan nuevas). Se piden solo las frescas.

Limite: lectura publica limitada por IP y licenciada para uso personal, no
comercial (mostrarla a terceros dentro de un producto pide un plan de API).
Una peticion por busqueda mas la cache de 15 minutos.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.services import experience_level
from app.services.apply_target import detect_ats
from app.services.external_jobs import http as external_http
from app.services.job_importer import html_to_text, parse_job_text_heuristic

ENDPOINT = "https://freehire.me/api/v1/jobs/search"
PAGE_SIZE = 50
_CACHE_TTL_SECONDS = 15 * 60
_search_cache: dict[str, dict[str, Any]] = {}

_LEVEL_FROM_NATIVE = {
    "intern": "internship",
    "junior": "entry",
    "middle": "mid",
    "senior": "senior",
    "lead": "lead",
    "staff": "lead",
    "principal": "lead",
    "c_level": "lead",
}
_LEVEL_TO_NATIVE = {"internship": "intern", "entry": "junior", "mid": "middle", "senior": "senior", "lead": "lead"}
_WORK_MODES = ("remote", "hybrid", "onsite")


class FreehireError(RuntimeError):
    pass


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    enr = raw.get("enrichment") or {}
    title = raw.get("title") or "Untitled position"
    company = raw.get("company") or "Unknown company"
    body = raw.get("description") or ""
    description = (html_to_text(body) if "<" in body else body).strip() or enr.get("summary") or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)
    known = {s["name"].lower() for s in parsed["skills_required"]}
    extra_skills = [
        {"name": s, "importance": "nice_to_have"} for s in raw.get("skills") or [] if s and s.lower() not in known
    ]
    requirements = [r["text"] for r in enr.get("requirements") or [] if isinstance(r, dict) and r.get("text")]

    remote_type = raw.get("work_mode") if raw.get("work_mode") in _WORK_MODES else parsed.get("remote_type")
    location = raw.get("location") or None
    if remote_type == "remote" and "global" in (raw.get("regions") or []):
        location = "Worldwide (remote)"

    url = raw.get("url") or None
    native = str(enr.get("seniority") or "").lower()
    has_salary = enr.get("salary_min") or enr.get("salary_max")
    return {
        "freehire_job_id": raw.get("public_slug"),
        "source": "freehire",
        "source_url": url,
        "apply_url": url,
        "apply_ats": detect_ats(url),
        "title": title,
        "company": company,
        "location": location,
        "remote_type": remote_type,
        "employment_type": enr.get("employment_type") or parsed["employment_type"],
        "seniority": _LEVEL_FROM_NATIVE.get(native) or experience_level.infer(title, description),
        "description": description,
        "requirements": requirements or parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"] + extra_skills,
        "salary_min": enr.get("salary_min"),
        "salary_max": enr.get("salary_max"),
        "salary_currency": enr.get("salary_currency") if has_salary else None,
        "posted_at": _parse_dt(raw.get("posted_at") or raw.get("created_at")),
    }


def _cleanup_cache(now: float) -> None:
    for k in [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]:
        _search_cache.pop(k, None)


async def search_freehire_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
    page: Optional[int] = None,
) -> dict[str, Any]:
    # shortcut: `location` no se manda (freehire pide codigos ISO de pais o
    # region, no texto libre); la elegibilidad la decide work_auth aguas abajo.
    # Mapear texto -> ISO si alguna vez hace falta filtrar por pais aqui.
    params: dict[str, Any] = {
        "limit": PAGE_SIZE,
        "sort": "posted_at",
        "order": "desc",
        "reality": "fresh",
    }
    if q:
        params["q"] = q
    if remote_type_filter in _WORK_MODES:
        params["work_mode"] = remote_type_filter
    native_level = _LEVEL_TO_NATIVE.get(experience_level_filter or "")
    if native_level:
        params["seniority"] = native_level
        params["seniority_include_unspecified"] = "true"
    if page:
        params["offset"] = (page - 1) * PAGE_SIZE

    try:
        resp = await external_http.get("freehire", ENDPOINT, params=params)
    except httpx.HTTPError as exc:
        raise FreehireError("Could not reach freehire (network error).") from exc
    if resp.status_code != 200:
        raise FreehireError(f"freehire request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise FreehireError("freehire returned a non-JSON response.") from exc

    now = time.time()
    results = []
    for raw in data.get("data") or []:
        if raw.get("closed_at"):
            continue
        normalized = _normalize(raw)
        if not experience_level.matches(normalized["seniority"], experience_level_filter):
            continue
        if normalized["freehire_job_id"]:
            _search_cache[normalized["freehire_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    meta = data.get("meta") or {}
    has_more = (meta.get("offset") or 0) + len(data.get("data") or []) < (meta.get("total") or 0)
    return {"results": results, "has_more": has_more}


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
