"""El formulario de una oferta de Greenhouse, leido por su API publica.

    GET boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}?questions=true

devuelve cada pregunta del formulario con su tipo, si es obligatoria y sus
opciones. Es la misma API de LECTURA que usa ats_boards.py, sin clave. Enviar
sigue exigiendo la clave del empleador (ver apply_target.py), asi que esta
pieza no abre ningun navegador: con la API basta para saber que se pregunta y
preparar cada respuesta.

Comprobado en vivo el 2026-10-12:
  * Las ofertas de la instancia europea (job-boards.eu.greenhouse.io) se leen
    por el mismo host; boards-api.eu.greenhouse.io ni siquiera resuelve.
  * Una pregunta puede traer varios campos: "Resume/CV" trae el archivo
    (input_file) y la alternativa en texto (resume_text). Se toma el archivo
    como campo principal y el texto como alternativa.
  * Las preguntas de diversidad pueden venir en tres sitios: `compliance`
    (EEOC de EE. UU.), `demographic_questions` (con otra forma) y, como hace
    Canonical, mezcladas con las preguntas normales. Las dos primeras se marcan
    por seccion; la tercera la detecta classify.py por el texto.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from app.services.job_importer import html_to_text

API_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}?questions=true"

#: Tipo de Greenhouse -> tipo propio. Lo que no esta aqui (input_hidden) no lo
#: llena una persona y no se muestra.
_TYPES = {
    "input_text": "text",
    "textarea": "textarea",
    "input_file": "file",
    "multi_value_single_select": "select",
    "multi_value_multi_select": "multiselect",
}

_JOB_PATH = re.compile(r"^/([^/]+)/jobs/(\d+)")


class FormUnavailable(RuntimeError):
    """El formulario no se pudo leer. El mensaje va directo a la interfaz."""


@dataclass
class FormField:
    key: str
    label: str
    #: text | textarea | file | select | multiselect
    type: str
    required: bool
    options: list[dict[str, str]] = field(default_factory=list)
    description: str = ""
    #: main | location | compliance | demographic
    section: str = "main"
    #: Otros nombres de campo de la misma pregunta (resume_text para resume).
    alternatives: list[str] = field(default_factory=list)


@dataclass
class ApplicationForm:
    ats: str
    board: str
    job_id: str
    #: Donde se publica la oferta (puede ser la web de la empresa).
    url: str
    #: Donde esta el formulario de Greenhouse que se llena (ver _form_url).
    form_url: str
    title: str
    company: str
    language: str
    fields: list[FormField]
    #: Avisos que el empleador pone en el formulario (p. ej. el de Greenhouse
    #: sobre su propio uso de IA al revisar candidaturas). Se muestran tal cual.
    notices: list[str] = field(default_factory=list)
    #: Greenhouse pide la educacion en un bloque aparte, con buscador de
    #: universidades. Si es obligatorio, el usuario lo completa en la revision.
    education_required: bool = False
    #: Donde se trabaja el puesto, tal como lo publica la empresa ("Remote -
    #: US", "Home based - Worldwide"). Decide respuestas que dependen de eso,
    #: como la autorizacion de trabajo.
    location: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_greenhouse_ref(value: Optional[str]) -> Optional[tuple[str, str]]:
    """(board, job_id) a partir de una URL de oferta o de un ats_job_id.

    Acepta:
      * job-boards.greenhouse.io/{board}/jobs/{id} (y boards., y .eu.)
      * boards.greenhouse.io/embed/job_app?for={board}&token={id}
      * greenhouse:{board}:{id}, el id que pone ats_boards.py

    Una pagina de empleo propia con ?gh_jid= no sirve: trae el id de la oferta
    pero no el tablero, y sin tablero la API no responde.
    """
    if not value:
        return None
    value = value.strip()
    if value.startswith("greenhouse:"):
        partes = value.split(":")
        if len(partes) == 3 and partes[1] and partes[2].isdigit():
            return partes[1], partes[2]
        return None

    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if not (host == "greenhouse.io" or host.endswith(".greenhouse.io")):
        return None
    if parsed.path.startswith("/embed/job_app"):
        query = parse_qs(parsed.query)
        board = (query.get("for") or [""])[0]
        token = (query.get("token") or [""])[0]
        return (board, token) if board and token.isdigit() else None
    match = _JOB_PATH.match(parsed.path)
    if match:
        return match.group(1), match.group(2)
    return None


def _plain(raw: Any) -> str:
    """Greenhouse manda el HTML escapado dos veces: &lt;p&gt;..."""
    if not raw:
        return ""
    return html_to_text(html_lib.unescape(str(raw))).strip()


def _options(values: Any) -> list[dict[str, str]]:
    salida = []
    for value in values or []:
        if isinstance(value, dict) and value.get("label") is not None:
            salida.append({"label": str(value["label"]).strip(), "value": str(value.get("value", value.get("id", "")))})
    return salida


def _question_to_field(question: dict[str, Any], section: str) -> Optional[FormField]:
    campos = [f for f in question.get("fields") or [] if isinstance(f, dict) and f.get("type") in _TYPES]
    if not campos:
        return None
    # El archivo manda sobre su alternativa en texto (Resume/CV, Cover Letter).
    principal = next((f for f in campos if f["type"] == "input_file"), campos[0])
    alternativas = [f["name"] for f in campos if f is not principal and f.get("name")]
    return FormField(
        key=str(principal.get("name") or ""),
        label=str(question.get("label") or "").strip(),
        type=_TYPES[principal["type"]],
        required=bool(question.get("required")),
        options=_options(principal.get("values")),
        description=_plain(question.get("description")),
        section=section,
        alternatives=alternativas,
    )


def _demographic_fields(block: Any) -> list[FormField]:
    """`demographic_questions` tiene otra forma: answer_options en vez de
    fields/values, y un id por pregunta en vez de un nombre de campo."""
    if not isinstance(block, dict):
        return []
    salida = []
    for question in block.get("questions") or []:
        if not isinstance(question, dict):
            continue
        tipo = "multiselect" if question.get("type") == "multi_value_multi_select" else "select"
        opciones = [
            {"label": str(o.get("label") or "").strip(), "value": str(o.get("id", ""))}
            for o in question.get("answer_options") or []
            if isinstance(o, dict)
        ]
        salida.append(
            FormField(
                key=f"demographic_{question.get('id')}",
                label=str(question.get("label") or "").strip(),
                type=tipo,
                required=bool(question.get("required")),
                options=opciones,
                section="demographic",
            )
        )
    return salida


def _form_url(listing_url: str, board: str, job_id: str) -> str:
    """El formulario de Greenhouse, aunque la oferta se publique en otra web.

    Coinbase publica en coinbase.com/careers/...?gh_jid= con el formulario en
    un iframe, y job-boards.greenhouse.io/coinbase/jobs/{id} redirige alli
    (comprobado en vivo). La URL de incrustar sirve el mismo formulario, con
    los mismos ids, en una pagina de Greenhouse."""
    host = (urlparse(listing_url).hostname or "").lower()
    if host == "greenhouse.io" or host.endswith(".greenhouse.io"):
        return listing_url
    return f"https://job-boards.greenhouse.io/embed/job_app?for={board}&token={job_id}"


def parse_form(data: dict[str, Any], board: str, job_id: str) -> ApplicationForm:
    fields: list[FormField] = []
    for seccion, preguntas in (("main", data.get("questions")), ("location", data.get("location_questions"))):
        for question in preguntas or []:
            campo = _question_to_field(question, seccion) if isinstance(question, dict) else None
            if campo and campo.key:
                fields.append(campo)
    for bloque in data.get("compliance") or []:
        if not isinstance(bloque, dict):
            continue
        for question in bloque.get("questions") or []:
            campo = _question_to_field(question, "compliance") if isinstance(question, dict) else None
            if campo and campo.key:
                fields.append(campo)
    fields.extend(_demographic_fields(data.get("demographic_questions")))

    notices = []
    if data.get("include_ai_disclaimer") and data.get("ai_disclaimer"):
        notices.append(_plain(data["ai_disclaimer"]))

    url = str(data.get("absolute_url") or f"https://job-boards.greenhouse.io/{board}/jobs/{job_id}")
    return ApplicationForm(
        ats="greenhouse",
        board=board,
        job_id=str(job_id),
        url=url,
        form_url=_form_url(url, board, str(job_id)),
        title=str(data.get("title") or ""),
        company=str(data.get("company_name") or board),
        language=str(data.get("language") or "en"),
        fields=fields,
        notices=[n for n in notices if n],
        education_required=data.get("education") == "education_required",
        location=str((data.get("location") or {}).get("name") or "").strip(),
    )


async def fetch_greenhouse_form(board: str, job_id: str) -> ApplicationForm:
    # Import aqui por lo mismo que en ats_boards: external_jobs importa
    # modulos de servicios y arriba se formaba un ciclo.
    from app.services.external_jobs import http as external_http

    try:
        resp = await external_http.get("greenhouse", API_URL.format(board=board, job_id=job_id))
    except Exception as exc:  # noqa: BLE001 - se traduce a un motivo legible
        raise FormUnavailable("No se pudo contactar a Greenhouse.") from exc
    status = getattr(resp, "status_code", 200)
    if status == 404:
        raise FormUnavailable("La oferta ya no existe en Greenhouse.")
    if status != 200:
        raise FormUnavailable(f"Greenhouse respondió {status} al pedir el formulario.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise FormUnavailable("Greenhouse devolvió un formulario ilegible.") from exc
    if not isinstance(data, dict):
        raise FormUnavailable("Greenhouse devolvió un formulario ilegible.")
    return parse_form(data, board, job_id)
