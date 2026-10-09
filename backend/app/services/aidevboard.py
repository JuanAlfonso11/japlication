"""AI Dev Jobs (aidevboard.com) -- empleos de AI/ML, gratis y sin clave.
Docs: https://aidevboard.com/openapi.yaml

Por que esta fuente: es la unica de la lista centrada en roles de AI/ML
(LLM, agentes, MLOps...), que es justo uno de los perfiles que se buscan.

Lo que la hace distinta de las demas:

* **`apply_url` apunta al ATS de la empresa** (Greenhouse, Ashby, Lever...),
  no a una pagina intermedia. Por eso se entrega como `apply_url` +
  `apply_ats` ya resueltos, igual que ats_boards.py, y `source_url` queda en
  la ficha de aidevboard.
* **Nivel nativo con vocabulario propio** (`junior|mid|senior|lead|principal`)
  que tambien acepta como filtro, asi que se filtra en el servidor y se
  traduce de vuelta con un mapa fijo. `normalize_native()` no sirve aqui:
  "mid" a secas no coincide con ninguna de sus reglas.
* **Remoto con ubicacion**: en una vacante remota `location` es la sede de la
  empresa, no donde se puede vivir. Si se pide remoto, la ubicacion NO se
  manda (filtraria por la sede y dejaria fuera casi todo). `global_remote`
  tampoco: exige prueba explicita de contratacion mundial y devuelve 0-1
  resultados por busqueda; la elegibilidad la decide `work_auth` aguas abajo,
  como en el resto de fuentes.

Limite: 200 peticiones por hora por IP (cabeceras x-ratelimit-*). Una
peticion por busqueda mas la cache de 15 minutos lo deja muy lejos.
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

ENDPOINT = "https://aidevboard.com/api/v1/jobs"
PAGE_SIZE = 50  # el maximo que acepta `limit`
_CACHE_TTL_SECONDS = 15 * 60
_search_cache: dict[str, dict[str, Any]] = {}

#: Su vocabulario -> nuestra taxonomia (experience_level.LEVELS).
_LEVEL_FROM_NATIVE = {
    "junior": "entry",
    "mid": "mid",
    "senior": "senior",
    "lead": "lead",
    "principal": "lead",
}
#: Nuestra taxonomia -> su filtro `level`. Sin "internship": no tienen ese
#: nivel, y mandar "junior" mezclaria puestos que no son practicas.
_LEVEL_TO_NATIVE = {"entry": "junior", "mid": "mid", "senior": "senior", "lead": "lead"}

_EMPLOYMENT_TYPES = {
    "full-time": "full_time",
    "part-time": "part_time",
    "contract": "contract",
    "freelance": "contract",
    "internship": "internship",
}

_WORKPLACES = ("remote", "hybrid", "onsite")


class AIDevBoardError(RuntimeError):
    pass


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _level(raw: dict[str, Any], title: str, description: str) -> Optional[str]:
    native = str(raw.get("experience_level") or "").strip().lower()
    return _LEVEL_FROM_NATIVE.get(native) or experience_level.infer(title, description)


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    title = raw.get("title") or "Untitled position"
    company = raw.get("company_name") or "Unknown company"
    body = raw.get("description") or ""
    description = (html_to_text(body) if "<" in body else body).strip() or "No description provided."

    parsed = parse_job_text_heuristic(description, title_hint=title, company_hint=company)

    known = {s["name"].lower() for s in parsed["skills_required"]}
    extra_skills = [
        {"name": t, "importance": "nice_to_have"}
        for t in raw.get("tags") or []
        if t and t.lower() not in known
    ]

    workplace = str(raw.get("workplace") or "").lower()
    remote_type = workplace if workplace in _WORKPLACES else parsed.get("remote_type")

    location = raw.get("location") or None
    if remote_type == "remote" and raw.get("remote_scope") == "global":
        location = "Worldwide (remote)"

    apply_url = raw.get("apply_url") or None
    job_type = str(raw.get("job_type") or "").lower()

    return {
        "aidevboard_job_id": str(raw.get("id")) if raw.get("id") else None,
        "source": "aidevboard",
        "source_url": raw.get("url") or apply_url,
        "apply_url": apply_url,
        "apply_ats": detect_ats(apply_url),
        "title": title,
        "company": company,
        "location": location,
        "remote_type": remote_type,
        "employment_type": _EMPLOYMENT_TYPES.get(job_type, parsed["employment_type"]),
        "seniority": _level(raw, title, description),
        "description": description,
        "requirements": parsed["requirements"],
        "responsibilities": parsed["responsibilities"],
        "skills_required": parsed["skills_required"] + extra_skills,
        # Su filtro de salario esta documentado en USD/ano.
        "salary_min": raw.get("salary_min"),
        "salary_max": raw.get("salary_max"),
        "salary_currency": "USD" if (raw.get("salary_min") or raw.get("salary_max")) else None,
        "posted_at": _parse_dt(raw.get("published_at") or raw.get("created_at")),
        "thumbnail": raw.get("company_logo_url") or None,
    }


def _cleanup_cache(now: float) -> None:
    stale = [k for k, v in _search_cache.items() if now - v["cached_at"] > _CACHE_TTL_SECONDS]
    for k in stale:
        _search_cache.pop(k, None)


async def search_aidevboard_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    experience_level_filter: Optional[str] = None,
    remote_type_filter: Optional[str] = None,
    page: Optional[int] = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": PAGE_SIZE}
    if q:
        params["q"] = q
    if remote_type_filter in _WORKPLACES:
        params["workplace"] = remote_type_filter
    loc = (location or "").strip()
    if loc and remote_type_filter != "remote" and loc.lower() not in ("remote", "remoto", "worldwide"):
        params["location"] = loc
    native_level = _LEVEL_TO_NATIVE.get(experience_level_filter or "")
    if native_level:
        params["level"] = native_level
    if page:
        params["page"] = page

    try:
        resp = await external_http.get("aidevboard", ENDPOINT, params=params)
    except httpx.HTTPError as exc:
        raise AIDevBoardError("Could not reach AI Dev Jobs (network error).") from exc

    if resp.status_code != 200:
        raise AIDevBoardError(f"AI Dev Jobs request failed with status {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise AIDevBoardError("AI Dev Jobs returned a non-JSON response.") from exc

    now = time.time()
    results = []
    for raw in data.get("jobs") or []:
        normalized = _normalize(raw)
        if remote_type_filter and normalized["remote_type"] and normalized["remote_type"] != remote_type_filter:
            continue
        if not experience_level.matches(normalized["seniority"], experience_level_filter):
            continue
        if normalized["aidevboard_job_id"]:
            _search_cache[normalized["aidevboard_job_id"]] = {"cached_at": now, "job": normalized}
        results.append(normalized)
    _cleanup_cache(now)

    return {"results": results, "has_more": bool(data.get("has_next"))}


def get_cached_result(job_id: str) -> Optional[dict[str, Any]]:
    entry = _search_cache.get(job_id)
    if entry is None:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _search_cache.pop(job_id, None)
        return None
    return entry["job"]
