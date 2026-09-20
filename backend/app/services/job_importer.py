"""Fetches a job posting URL and parses it into the structured shape used by
the `jobs` table / `Job` schema.

Strategy (in order of preference):
1. JSON-LD `schema.org/JobPosting` — many job boards (LinkedIn, Greenhouse,
   Lever, Workday, etc.) embed a `<script type="application/ld+json">` block
   with `@type: "JobPosting"`. This is the most reliable source.
2. Heuristic HTML/text extraction — look for common section headers
   ("Requirements", "Responsibilities", "Qualifications", "Nice to have", ...)
   and bullet lists, plus a regex-based skills scan over the whole text using
   the built-in skills taxonomy.

Network/parsing errors are always converted into a clean
`JobImportError` rather than propagating raw exceptions; the router
turns it into a 422.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

from app.services.skills_taxonomy import extract_skills_from_text
from app.services.url_guard import UnsafeUrlError, validate_public_http_url

logger = logging.getLogger(__name__)


class JobImportError(RuntimeError):
    """This URL could not be turned into a job posting.

    A service raising HTTPException ties it to the transport: the every-2-hours
    sweep and run_daily_sweep.py call this code with no request in flight, and
    a FastAPI exception there is meaningless - every other one of the 15 job
    services already raises its own error and lets the router translate it.
    The message is written for the end user, because the router forwards it.
    """


USER_AGENT = (
    "Mozilla/5.0 (compatible; JobFlowAI/1.0; +https://jobflow.ai/bot) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

SECTION_HEADERS = {
    "requirements": [
        "requirements", "requisitos", "qualifications", "what you'll need",
        "what you need", "must have", "minimum qualifications", "skills required",
    ],
    "nice_to_have": [
        "nice to have", "preferred qualifications", "bonus points", "deseable",
        # "plus" a secas estuvo aqui y reclasificaba TODO lo obligatorio como
        # deseable. En espanol "plus" es casi siempre una prestacion -- "plus
        # de transporte", "plus de nocturnidad" -- y en ingles aparece dentro
        # de palabras como "surplus". Medido: una oferta con "Plus de
        # transporte incluido" antes de los requisitos dejaba las cinco
        # habilidades obligatorias marcadas como deseables, el match subia de
        # 37,5 a 50,0 y "lo que te falta" salia vacio.
        #
        # Solo formas que encabezan una seccion. El corte parte el texto EN el
        # marcador y trata como deseable lo que viene DESPUES, asi que una
        # frase suelta tipo "Kubernetes is a plus" -- donde la habilidad va
        # antes -- nunca se pudo clasificar por esta via, ni con el marcador
        # anterior. Anadirla solo meteria un punto de corte en el lado
        # equivocado. En esa forma la habilidad se queda como obligatoria, que
        # es el error conservador: aparece en "lo que te falta" en vez de
        # desaparecer del calculo.
        "preferred skills", "nice-to-have", "deseables", "se valora", "valorable",
    ],
    "responsibilities": [
        "responsibilities", "responsabilidades", "what you'll do", "what you will do",
        "duties", "the role", "your role", "day to day", "day-to-day",
    ],
}

REMOTE_KEYWORDS = {
    "remote": "remote",
    "fully remote": "remote",
    "remoto": "remote",
    "hybrid": "hybrid",
    "híbrido": "hybrid",
    "hibrido": "hybrid",
    "on-site": "onsite",
    "onsite": "onsite",
    "in-office": "onsite",
    "presencial": "onsite",
}

EMPLOYMENT_KEYWORDS = {
    "full-time": "full_time",
    "full time": "full_time",
    "tiempo completo": "full_time",
    "part-time": "part_time",
    "part time": "part_time",
    "medio tiempo": "part_time",
    "contract": "contract",
    "contractor": "contract",
    "freelance": "contract",
    "internship": "internship",
    "intern": "internship",
    "pasantía": "internship",
    "becario": "internship",
}

SENIORITY_KEYWORDS = [
    "intern", "junior", "jr.", "mid-level", "mid level", "senior", "sr.",
    "staff", "principal", "lead", "head of", "director", "vp", "entry-level", "entry level",
]

YEARS_REQUIREMENT_RE = re.compile(
    r"(\d+)\s*\+?\s*(?:-|a|to)?\s*(\d+)?\s*(?:years|años|anos|yrs)", re.IGNORECASE
)


# Job pages are big, but not this big. Without a ceiling, pointing the
# importer at a multi-gigabyte file would buffer all of it into the
# container's memory before anything got parsed.
MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024

# Enough to get through the usual "www -> apex -> /jobs/123" chains without
# letting a redirect loop run forever.
MAX_REDIRECTS = 5


async def fetch_html(url: str) -> str:
    """Solo el HTML. Ver fetch_html_with_url cuando tambien haga falta saber
    donde se acabo aterrizando."""
    html, _final = await fetch_html_with_url(url)
    return html


async def fetch_html_with_url(url: str) -> tuple[str, str]:
    """Downloads a job posting page, refusing anything that points at
    internal infrastructure.

    Redirects are followed by hand rather than with httpx's
    `follow_redirects=True`, because that only ever sees the URL the caller
    passed: a public page answering 302 with `Location: http://localhost:8000`
    would be fetched without a second thought. Validating every hop is the
    whole point — see app/services/url_guard.py.
    """
    try:
        current = validate_public_http_url(url)
    except UnsafeUrlError as exc:
        raise JobImportError(str(exc)) from exc

    try:
        async with httpx.AsyncClient(
            # Two timeouts, not one. `timeout=15.0` alone is per-operation:
            # a server dripping one byte every 14 seconds resets it forever
            # and the request never ends. The pool-wide deadline is what
            # actually bounds the whole exchange.
            timeout=httpx.Timeout(15.0, connect=10.0),
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                # Streamed, not `client.get()`. A plain get() buffers the
                # entire body into memory *before* returning, so checking
                # len(resp.content) afterwards was checking a limit that had
                # already been blown: a chunked response (no Content-Length)
                # of any size would OOM the container first. Same fix that
                # api/v1/routers/profile.py already applies to CV uploads.
                async with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise JobImportError("could not parse job posting")
                        # Relative Locations are normal; resolve against the
                        # URL we actually fetched before re-validating.
                        next_url = str(resp.url.join(location))
                        try:
                            current = validate_public_http_url(next_url)
                        except UnsafeUrlError as exc:
                            raise JobImportError(str(exc)) from exc
                        # Leaving the `async with` closes this response
                        # without reading its body — a redirect has nothing
                        # worth downloading.
                        continue

                    resp.raise_for_status()

                    # Cheap rejection first, when the server is honest about
                    # the size. The streaming loop below is what actually
                    # enforces the cap, for servers that are not.
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > MAX_DOWNLOAD_BYTES:
                        raise JobImportError("La página es demasiado grande para importarla.")

                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_DOWNLOAD_BYTES:
                            # Abandon the connection right here; do not read
                            # the rest of whatever the server wants to send.
                            raise JobImportError("La página es demasiado grande para importarla.")
                        chunks.append(chunk)

                    body = b"".join(chunks)
                    encoding = resp.encoding or "utf-8"
                    # `current` y no `url`: es la URL del ultimo salto, que es
                    # donde de verdad vive la pagina. Un acortador o un
                    # redirector del portal devolvia antes la URL de entrada,
                    # asi que la vacante quedaba guardada apuntando al
                    # redirector -- la deduplicacion por source_url fallaba y
                    # "ver oferta original" reabria el salto, no el destino.
                    try:
                        return body.decode(encoding, errors="replace"), current
                    except LookupError:
                        # Server declared a charset Python does not know.
                        return body.decode("utf-8", errors="replace"), current

            raise JobImportError("Demasiadas redirecciones.")
    except JobImportError:
        raise
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        raise JobImportError("could not parse job posting") from exc


def _find_jsonld_jobposting(soup: BeautifulSoup) -> Optional[dict[str, Any]]:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        candidates: list[Any] = data if isinstance(data, list) else [data]
        # Some sites nest the posting under "@graph"
        expanded: list[Any] = []
        for c in candidates:
            if isinstance(c, dict) and "@graph" in c and isinstance(c["@graph"], list):
                expanded.extend(c["@graph"])
            else:
                expanded.append(c)

        for item in expanded:
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if any(str(t).lower() == "jobposting" for t in types if t):
                return item
    return None


def _text_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def html_to_text(html_fragment: Optional[str]) -> str:
    if not html_fragment:
        return ""
    frag_soup = BeautifulSoup(html_fragment, "lxml")
    return frag_soup.get_text(separator="\n", strip=True)


def _extract_bullets(html_fragment: Optional[str]) -> list[str]:
    if not html_fragment:
        return []
    frag_soup = BeautifulSoup(html_fragment, "lxml")
    bullets = [li.get_text(strip=True) for li in frag_soup.find_all("li")]
    bullets = [b for b in bullets if b]
    if bullets:
        return bullets
    # No <li> tags: split lines as a fallback
    text = frag_soup.get_text(separator="\n", strip=True)
    return [line.strip("-• \t") for line in text.split("\n") if line.strip()]


def _build_skills_required(text: str) -> list[dict[str, str]]:
    """Extract skills from full text and split into required vs nice_to_have
    using proximity to nice-to-have section keywords."""
    nice_to_have_markers = SECTION_HEADERS["nice_to_have"]
    lowered = text.lower()

    # Find the char offset where a "nice to have" section starts, if any.
    #
    # Como palabra completa, no como subcadena: `find` hacia que "surplus"
    # contara como la cabecera "plus" y partiera la lista en el sitio
    # equivocado. Todo lo que quedaba despues pasaba de obligatorio a
    # deseable, que es el peor resultado posible -- silenciosamente
    # incorrecto en el numero que da sentido a la app.
    nice_to_have_start = None
    for marker in nice_to_have_markers:
        match = re.search(r"(?<![a-z0-9])" + re.escape(marker) + r"(?![a-z0-9])", lowered)
        if match and (nice_to_have_start is None or match.start() < nice_to_have_start):
            nice_to_have_start = match.start()

    if nice_to_have_start is not None:
        required_text = text[:nice_to_have_start]
        nice_text = text[nice_to_have_start:]
    else:
        required_text = text
        nice_text = ""

    required_skills = extract_skills_from_text(required_text)
    nice_skills = [s for s in extract_skills_from_text(nice_text) if s not in required_skills]

    result = [{"name": s, "importance": "required"} for s in required_skills]
    result += [{"name": s, "importance": "nice_to_have"} for s in nice_skills]
    return result


def _extract_section(text: str, header_keys: list[str]) -> list[str]:
    """Heuristic: find a line matching one of the header keywords, then collect
    subsequent bullet-like lines until the next recognized header or blank gap."""
    lines = [l.strip() for l in text.split("\n")]
    all_headers = [h for group in SECTION_HEADERS.values() for h in group]

    start_idx = None
    for i, line in enumerate(lines):
        low = line.lower().strip(" :#-")
        if any(low == h or low.startswith(h) for h in header_keys) and len(low) < 60:
            start_idx = i + 1
            break
    if start_idx is None:
        return []

    collected: list[str] = []
    blank_run = 0
    for line in lines[start_idx:]:
        stripped = line.strip()
        low = stripped.lower().strip(" :#-")
        if not stripped:
            # Las dos ramas de este if hacian `continue`, asi que la seccion
            # no terminaba nunca: el comentario describia un corte que el
            # codigo no hacia. Medido sobre una oferta real, "Requisitos" se
            # tragaba 40 lineas de "Sobre nosotros", proceso de seleccion,
            # politica de privacidad y el correo de RRHH -- y todo eso entraba
            # en el score y en el prompt que adapta el CV.
            #
            # Una linea en blanco suelta se tolera (las listas las llevan);
            # dos seguidas son un cambio de seccion. Antes de recoger nada
            # no cuentan: el hueco entre la cabecera y su primer elemento.
            if collected:
                blank_run += 1
                if blank_run >= 2:
                    break
            continue
        blank_run = 0
        if any(low == h or low.startswith(h) for h in all_headers) and len(low) < 60:
            break
        cleaned = stripped.lstrip("-•*• \t")
        if cleaned:
            collected.append(cleaned)
        if len(collected) >= 40:
            break
    return collected


def _extract_seniority(text: str) -> Optional[str]:
    lowered = text.lower()
    for kw in SENIORITY_KEYWORDS:
        if kw in lowered:
            if kw in ("jr.",):
                return "junior"
            if kw in ("sr.",):
                return "senior"
            return kw.replace("-", " ")
    return None


def _extract_remote_type(text: str) -> Optional[str]:
    lowered = text.lower()
    for kw, val in REMOTE_KEYWORDS.items():
        if kw in lowered:
            return val
    return None


def _extract_employment_type(text: str) -> Optional[str]:
    lowered = text.lower()
    for kw, val in EMPLOYMENT_KEYWORDS.items():
        if kw in lowered:
            return val
    return None


#: Como se escribe una fecha limite en una oferta, en los dos idiomas. Solo
#: formas explicitas: "aplica pronto" o "plazas limitadas" no son una fecha, y
#: adivinar una es peor que no tener ninguna -- un aviso de "te quedan 2 dias"
#: basado en una suposicion hace que dejes de fiarte de todos los avisos.
_DEADLINE_MARKERS = (
    "fecha limite", "fecha límite", "plazo de inscripcion", "plazo de inscripción",
    "postula antes del", "aplica antes del", "cierre de postulaciones",
    "las candidaturas se cierran", "recepcion de candidaturas hasta",
    "application deadline", "apply before", "applications close",
    "closing date", "deadline for applications", "last day to apply",
)

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

#: 2026-03-15 · 15/03/2026 · 15 de marzo de 2026 · March 15, 2026
_DATE_PATTERNS = (
    re.compile(r"(?P<y>20\d{2})-(?P<m>\d{1,2})-(?P<d>\d{1,2})"),
    re.compile(r"(?P<d>\d{1,2})[/.-](?P<m>\d{1,2})[/.-](?P<y>20\d{2})"),
    re.compile(r"(?P<d>\d{1,2})\s+de\s+(?P<mon>[a-zá-ú]+)\s+de\s+(?P<y>20\d{2})", re.IGNORECASE),
    re.compile(r"(?P<mon>[a-z]+)\s+(?P<d>\d{1,2}),?\s+(?P<y>20\d{2})", re.IGNORECASE),
)


def _extract_deadline(text: str) -> Optional[date]:
    """La fecha limite declarada en el texto, o None.

    Solo mira los 120 caracteres que siguen a un marcador explicito: una
    oferta esta llena de fechas (cuando se fundo la empresa, desde cuando
    existe el equipo, la fecha de publicacion) y coger la primera que aparezca
    daria un plazo inventado. Mejor ninguna fecha que una equivocada.
    """
    if not text:
        return None
    lowered = text.lower()
    for marker in _DEADLINE_MARKERS:
        idx = lowered.find(marker)
        if idx == -1:
            continue
        window = text[idx : idx + 120]
        for pattern in _DATE_PATTERNS:
            match = pattern.search(window)
            if not match:
                continue
            groups = match.groupdict()
            month = (
                _MONTHS.get((groups.get("mon") or "").lower())
                if groups.get("mon")
                else int(groups["m"])
            )
            if not month:
                continue
            try:
                found = date(int(groups["y"]), month, int(groups["d"]))
            except ValueError:
                continue
            # Una "fecha limite" en el pasado es casi siempre otra cosa mal
            # leida, y avisar de un plazo vencido no ayuda a nadie.
            if found >= date.today():
                return found
    return None


def parse_jobposting_jsonld(item: dict[str, Any], fallback_text: str = "") -> dict[str, Any]:
    title = _text_or_none(item.get("title")) or "Untitled position"

    org = item.get("hiringOrganization")
    company = None
    if isinstance(org, dict):
        company = _text_or_none(org.get("name"))
    elif isinstance(org, str):
        company = org
    company = company or "Unknown company"

    location = None
    job_location = item.get("jobLocation")
    if isinstance(job_location, list) and job_location:
        job_location = job_location[0]
    if isinstance(job_location, dict):
        address = job_location.get("address")
        if isinstance(address, dict):
            parts = [
                _text_or_none(address.get("addressLocality")),
                _text_or_none(address.get("addressRegion")),
                _text_or_none(address.get("addressCountry")),
            ]
            location = ", ".join([p for p in parts if p]) or None
        elif isinstance(address, str):
            location = address

    is_remote = item.get("jobLocationType")
    remote_type = None
    if is_remote and "telecommute" in str(is_remote).lower():
        remote_type = "remote"

    description_html = item.get("description") or ""
    description_text = html_to_text(description_html) or fallback_text

    employment_type_raw = item.get("employmentType")
    employment_type = None
    if employment_type_raw:
        raw = employment_type_raw[0] if isinstance(employment_type_raw, list) else employment_type_raw
        raw = str(raw).lower().replace("_", " ")
        employment_type = EMPLOYMENT_KEYWORDS.get(raw) or _extract_employment_type(raw)

    salary_min = salary_max = salary_currency = None
    base_salary = item.get("baseSalary")
    if isinstance(base_salary, dict):
        salary_currency = _text_or_none(base_salary.get("currency"))
        value = base_salary.get("value")
        if isinstance(value, dict):
            salary_min = value.get("minValue")
            salary_max = value.get("maxValue")
            if salary_min is None and value.get("value") is not None:
                salary_min = salary_max = value.get("value")

    posted_at = None
    date_posted = item.get("datePosted")
    if date_posted:
        try:
            posted_at = datetime.fromisoformat(str(date_posted).replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    # `validThrough` es el campo de schema.org para esto, asi que cuando la
    # pagina lo trae no hay que adivinar nada. El texto solo se mira si falta.
    deadline = None
    valid_through = item.get("validThrough")
    if valid_through:
        try:
            deadline = datetime.fromisoformat(str(valid_through).replace("Z", "+00:00")).date()
        except ValueError:
            deadline = None
    if deadline is None:
        deadline = _extract_deadline(description_text)

    full_text_for_scan = description_text
    requirements = _extract_section(description_text, SECTION_HEADERS["requirements"]) or []
    responsibilities = _extract_section(description_text, SECTION_HEADERS["responsibilities"]) or []
    skills_required = _build_skills_required(full_text_for_scan)
    remote_type = remote_type or _extract_remote_type(full_text_for_scan)
    seniority = _extract_seniority(title + " " + full_text_for_scan)
    employment_type = employment_type or _extract_employment_type(full_text_for_scan)

    return {
        "title": title,
        "company": company,
        "location": location,
        "remote_type": remote_type,
        "employment_type": employment_type,
        "seniority": seniority,
        "description": description_text.strip() or "No description provided.",
        "requirements": requirements,
        "responsibilities": responsibilities,
        "skills_required": skills_required,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": salary_currency,
        "posted_at": posted_at,
        "deadline": deadline,
    }


def parse_job_text_heuristic(text: str, title_hint: Optional[str] = None, company_hint: Optional[str] = None) -> dict[str, Any]:
    """Fallback heuristic parser for plain text / HTML-stripped job descriptions
    with no JSON-LD available (or for manually pasted descriptions)."""
    text = text.strip()
    if not text:
        raise JobImportError("could not parse job posting")

    lines = [l for l in text.split("\n") if l.strip()]
    title = title_hint or (lines[0].strip() if lines else "Untitled position")
    company = company_hint or "Unknown company"

    requirements = _extract_section(text, SECTION_HEADERS["requirements"])
    responsibilities = _extract_section(text, SECTION_HEADERS["responsibilities"])
    skills_required = _build_skills_required(text)
    remote_type = _extract_remote_type(text)
    employment_type = _extract_employment_type(text)
    seniority = _extract_seniority(title + " " + text)

    return {
        "title": title,
        "company": company,
        "location": None,
        "remote_type": remote_type,
        "employment_type": employment_type,
        "seniority": seniority,
        "description": text,
        "requirements": requirements,
        "responsibilities": responsibilities,
        "skills_required": skills_required,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "posted_at": None,
        "deadline": _extract_deadline(text),
    }


def _unparseable(stage: str, exc: BaseException, url: Optional[str] = None) -> JobImportError:
    """Turn an unexpected parser crash into the user-facing 422 — but leave a trace.

    Every one of these used to be a bare `except Exception` raising the same
    flat message. That made two completely different situations
    indistinguishable: a page that genuinely has no job posting on it (normal,
    nothing to do) and a bug in our own extraction code (needs fixing). And
    because error_middleware deliberately does not record 4xx responses, the
    bug left no trace anywhere — the importer could rot for weeks with zero
    evidence.

    The user still sees the same friendly 422. The traceback goes to the log.
    """
    logger.warning(
        "job import: %s failed for %s — %s: %s",
        stage,
        url or "<no url>",
        type(exc).__name__,
        exc,
        exc_info=exc,
    )
    return JobImportError("could not parse job posting")


def parse_job_html(html: str, url: Optional[str] = None) -> dict[str, Any]:
    """Pure parsing function (no network I/O) so it's easily unit-testable.
    Tries JSON-LD JobPosting first, falls back to heuristic text extraction.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:  # pragma: no cover - lxml parser is very lenient
        raise _unparseable("soup", exc, url) from exc

    jsonld_item = _find_jsonld_jobposting(soup)
    if jsonld_item:
        page_text = soup.get_text(separator="\n", strip=True)
        try:
            parsed = parse_jobposting_jsonld(jsonld_item, fallback_text=page_text)
        except Exception as exc:
            raise _unparseable("jsonld", exc, url) from exc
    else:
        # Strip script/style, then use visible text heuristically.
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title_tag = soup.find("h1") or soup.find("title")
        title_hint = title_tag.get_text(strip=True) if title_tag else None
        page_text = soup.get_text(separator="\n", strip=True)
        if not page_text or len(page_text) < 20:
            # Not a bug — the page really has no readable text. No log.
            raise JobImportError("could not parse job posting")
        try:
            parsed = parse_job_text_heuristic(page_text, title_hint=title_hint)
        except JobImportError:
            raise
        except Exception as exc:
            raise _unparseable("heuristic", exc, url) from exc

    parsed["source_url"] = url
    parsed["raw_html"] = html
    return parsed


async def import_job_from_url(url: str) -> dict[str, Any]:
    html = await fetch_html(url)
    try:
        # En un hilo, no en el event loop. parse_job_html es BeautifulSoup +
        # lxml + los extractores heuristicos, todo sincrono, y escala con el
        # tamano de la pagina: medido, 13,2 s con los 5 MiB que MAX_DOWNLOAD_
        # BYTES deja pasar. Durante esos 13 s uvicorn no atendia NADA -- ni
        # login, ni swipes, ni los heartbeats de las tareas programadas; un
        # latido de 100 ms dio cero pulsos en todo el bloqueo. Con to_thread,
        # el mismo trabajo deja el hueco maximo en 0,2 s.
        return await asyncio.to_thread(parse_job_html, html, url)
    except JobImportError:
        raise
    except Exception as exc:
        raise _unparseable("import", exc, url) from exc
