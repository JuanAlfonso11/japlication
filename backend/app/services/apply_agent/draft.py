"""El borrador de una candidatura: cada campo del formulario con su respuesta.

Tres pasadas:

1. Determinista. Lo que el perfil contesta sin interpretar: nombre, correo,
   telefono, enlaces, el CV, y las respuestas guardadas del perfil cuando la
   pregunta trata del mismo tema (autorizacion, patrocinio, salario...). Un
   "Si"/"No" guardado se traduce a la opcion "Yes"/"No" del formulario.
2. El LLM, para lo que queda: elegir una opcion o redactar una respuesta, SOLO
   con los hechos del perfil (facts.py). Si no le alcanza, dice "no se".
3. Cierre: lo que nadie pudo contestar queda para el usuario, y se calculan
   los motivos de revision -- los frenos del modo automatico.

Lo que el agente NUNCA contesta, pase lo que pase:
  * consentimientos y declaraciones (es la firma del usuario);
  * preguntas sensibles (diversidad, salud, nacionalidad, edad...). Si son
    voluntarias se dejan en blanco, que es una respuesta valida y la mas
    prudente; si son obligatorias, las responde el usuario.

Y si el formulario tiene una politica contra contenido generado con IA, el
LLM no participa en absoluto: solo se llena lo que viene tal cual del perfil.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from app.core.config import settings
from app.services.apply_agent.classify import (
    KIND_CHOICE,
    KIND_CONSENT,
    KIND_DOCUMENT,
    KIND_IDENTITY,
    KIND_OPEN,
    KIND_PERSONAL,
    KIND_SALARY,
    KIND_SENSITIVE,
    KIND_TEXT,
    KIND_WORK_AUTH,
    classify,
    identity_key,
    is_location_question,
    mentions_ai_policy,
    norm,
    topic_of,
)
from app.services.apply_agent.facts import screening_for
from app.services.apply_agent.greenhouse import ApplicationForm, FormField

logger = logging.getLogger(__name__)

FILLED = "filled"
NEEDS_USER = "needs_user"
SKIPPED = "skipped"
_PENDING = "pending"  # solo durante la construccion: candidato para el LLM

SOURCE_PROFILE = "profile"
SOURCE_SCREENING = "screening"
SOURCE_AI = "ai"
SOURCE_NONE = "none"

#: Motivos por los que un borrador no puede salir solo, aunque el modo
#: automatico este activado. El texto es el que ve el usuario.
REVIEW_REASONS: dict[str, str] = {
    "ai_policy": "La empresa prohíbe respuestas generadas con IA: el agente no redactó nada.",
    "consent": "Hay declaraciones o consentimientos que solo tú puedes aceptar.",
    "sensitive": "Hay preguntas sensibles obligatorias que solo tú respondes.",
    "personal": "Hay preguntas sobre tu historial o tus relaciones que solo tú puedes responder.",
    "salary": "Pregunta por salario: revísalo antes de enviar.",
    "work_auth": "Pregunta por autorización de trabajo, visa o país: revísalo antes de enviar.",
    "open_text": "Hay respuestas abiertas redactadas por la IA: léelas antes de enviar.",
    "needs_user": "Hay campos obligatorios que el agente no pudo responder con tu perfil.",
    "education": "El formulario exige el bloque de educación, que se llena a mano.",
}

_TEXT_LIMIT = {"text": 300, "textarea": 2000}


@dataclass
class FieldDraft:
    key: str
    label: str
    type: str
    required: bool
    section: str
    kind: str
    options: list[dict[str, str]] = field(default_factory=list)
    topic: Optional[str] = None
    #: Texto, o el `value` de la opcion, o la lista de `value`s si es multiple.
    value: Any = None
    #: Lo que ve el usuario: el texto, o la etiqueta de la(s) opcion(es).
    display: Optional[str] = None
    source: str = SOURCE_NONE
    status: str = _PENDING
    reason: Optional[str] = None
    alternatives: list[str] = field(default_factory=list)


@dataclass
class Draft:
    ats: str
    board: str
    job_id: str
    url: str
    form_url: str
    title: str
    company: str
    language: str
    ai_policy: bool
    fields: list[FieldDraft]
    notices: list[str] = field(default_factory=list)
    education_required: bool = False
    review_reasons: list[str] = field(default_factory=list)
    auto_eligible: bool = False
    used_ai: bool = False

    def stats(self) -> dict[str, int]:
        obligatorios = [f for f in self.fields if f.required]
        return {
            "total": len(self.fields),
            "required": len(obligatorios),
            "filled": sum(1 for f in self.fields if f.status == FILLED),
            "required_filled": sum(1 for f in obligatorios if f.status == FILLED),
            "needs_user": sum(1 for f in self.fields if f.status == NEEDS_USER),
            "by_ai": sum(1 for f in self.fields if f.source == SOURCE_AI),
        }

    def to_dict(self) -> dict[str, Any]:
        datos = asdict(self)
        datos["stats"] = self.stats()
        datos["review_reason_texts"] = [REVIEW_REASONS[r] for r in self.review_reasons if r in REVIEW_REASONS]
        return datos


# ---------------------------------------------------------------- opciones

_YES = {"yes", "si", "y", "true"}
_NO = {"no", "n", "false"}

#: Nombres de pais que el perfil puede traer y como suelen aparecer en las
#: opciones de un formulario en ingles. Solo los de la region del usuario; el
#: resto lo resuelve el LLM o el usuario.
_COUNTRY_ALIASES = {
    "republica dominicana": "dominican republic",
    "rd": "dominican republic",
    "do": "dominican republic",
    "estados unidos": "united states",
    "eeuu": "united states",
    "ee. uu.": "united states",
    "usa": "united states",
    "mexico": "mexico",
    "espana": "spain",
    "puerto rico": "puerto rico",
    "colombia": "colombia",
}


def _option_by_label(options: list[dict[str, str]], label: str) -> Optional[dict[str, str]]:
    objetivo = norm(label)
    for opcion in options:
        if norm(opcion["label"]) == objetivo:
            return opcion
    return None


def _yes_no(answer: str) -> Optional[str]:
    """"Sí, tengo autorización" -> "yes". Solo la primera palabra cuenta: una
    respuesta que no empieza por si/no no es un si/no, y adivinar seria peor."""
    primera = norm(answer).replace(",", " ").replace(".", " ").split()
    if not primera:
        return None
    if primera[0] in _YES:
        return "yes"
    if primera[0] in _NO:
        return "no"
    return None


def _yes_no_option(options: list[dict[str, str]], answer: str) -> Optional[dict[str, str]]:
    sentido = _yes_no(answer)
    if sentido is None:
        return None
    candidatas = [o for o in options if _yes_no(o["label"]) == sentido]
    # Solo si no hay ambiguedad: "Yes, I am authorized" y "Yes, but I need a
    # visa" son dos "si" distintos, y elegir uno es interpretar.
    return candidatas[0] if len(candidatas) == 1 else None


def _country_option(options: list[dict[str, str]], country: str) -> Optional[dict[str, str]]:
    if not country:
        return None
    nombre = norm(country)
    return _option_by_label(options, _COUNTRY_ALIASES.get(nombre, nombre))


def _set(fd: FieldDraft, value: Any, display: str, source: str) -> None:
    fd.value, fd.display, fd.source, fd.status, fd.reason = value, display, source, FILLED, None


def _to_user(fd: FieldDraft, reason: str) -> None:
    """Lo responde el usuario. Si es opcional, se deja en blanco."""
    fd.status = NEEDS_USER if fd.required else SKIPPED
    fd.reason = reason


# ---------------------------------------------------------------- pasada 1

#: Temas cuya respuesta guardada contesta la pregunta sin interpretarla.
_COPY_TOPICS = {"work_auth", "sponsorship", "salary", "start_date"}


def _deterministic(fd: FieldDraft, field: FormField, facts: dict[str, Any], ai_policy: bool) -> None:
    if fd.kind == KIND_DOCUMENT:
        if field.key == "resume" or "resume" in norm(field.label) or norm(field.label).startswith("cv"):
            _set(fd, "master_cv", "Tu CV maestro (PDF)", SOURCE_PROFILE)
        else:
            _to_user(fd, "Archivo que no es el CV (p. ej. carta de presentación): adjúntalo tú si quieres.")
        return

    if fd.kind == KIND_CONSENT:
        _to_user(fd, "Declaración o consentimiento: solo tú puedes aceptarlo.")
        return

    if fd.kind == KIND_SENSITIVE:
        if fd.required:
            _to_user(fd, "Pregunta sensible obligatoria: el agente no la responde.")
        else:
            _to_user(fd, "Pregunta sensible voluntaria: se deja en blanco.")
        return

    if fd.kind == KIND_PERSONAL:
        _to_user(fd, "Dato personal que tu perfil no registra: respóndelo tú.")
        return

    if fd.kind == KIND_IDENTITY:
        clave = identity_key(field) or ""
        valor = facts.get(clave) or ""
        if clave == "preferred_name":
            fd.status, fd.reason = SKIPPED, "Opcional."
            return
        if valor and field.type in ("text", "textarea"):
            _set(fd, valor, valor, SOURCE_PROFILE)
        elif valor and field.type == "select":
            opcion = _country_option(field.options, valor) or _option_by_label(field.options, valor)
            if opcion:
                _set(fd, opcion["value"], opcion["label"], SOURCE_PROFILE)
        if fd.status == _PENDING:
            _to_user(fd, "Tu dato no coincide con ninguna opción del formulario." if valor else "Falta en tu perfil.")
        return

    # Pais: si el perfil lo tiene y el formulario lo ofrece tal cual, no hace
    # falta interpretar nada. El pais del perfil es donde VIVE el usuario: no
    # contesta de que pais es ciudadano.
    etiqueta = norm(field.label)
    if field.type == "select" and "country" in etiqueta and "citizen" not in etiqueta:
        opcion = _country_option(field.options, facts.get("country") or "")
        if opcion:
            _set(fd, opcion["value"], opcion["label"], SOURCE_PROFILE)
            return

    guardada = screening_for(facts, fd.topic)
    if not guardada:
        return  # pendiente para el LLM
    if field.type == "select":
        opcion = _yes_no_option(field.options, guardada)
        if opcion:
            _set(fd, opcion["value"], opcion["label"], SOURCE_SCREENING)
    elif field.type in _TEXT_LIMIT and ai_policy and fd.topic in _COPY_TOPICS:
        # Sin IA permitida, la respuesta guardada va tal cual: son palabras del
        # propio usuario. Sin politica de IA, el LLM la recibe como pista y la
        # adapta: las guardadas estan en espanol y el formulario casi siempre
        # en ingles, y "anos de experiencia en tu rol principal" no contesta
        # "anos de experiencia con Kubernetes" aunque compartan tema.
        _set(fd, guardada[: _TEXT_LIMIT[field.type]], guardada, SOURCE_SCREENING)


# ---------------------------------------------------------------- pasada 2

SYSTEM_PROMPT = """Llenas formularios de empleo en nombre de un candidato.

Reglas, sin excepciones:
- Solo puedes usar los HECHOS DEL CANDIDATO que se te dan. Nunca inventes
  experiencia, empresas, fechas, cifras, titulos, notas, habilidades ni logros.
- Si los hechos no alcanzan para responder con certeza, responde
  {"status": "unknown"}. Un "unknown" es una buena respuesta: la completa el
  candidato. Una respuesta inventada es la peor posible.
- Que los hechos no mencionen algo NO significa que la respuesta sea "No". En
  preguntas de si/no sobre historial, relaciones, situacion legal o
  migratoria, responde "unknown" salvo que un hecho lo diga explicitamente.
- Nunca deduzcas un dato de otro distinto: un usuario de GitHub no es un
  usuario de GitLab, y una universidad no es un empleador salvo que figure
  como experiencia.
- Nunca redactes una declaracion, un acuse de recibo o un consentimiento
  ("I understand...", "I agree..."): eso solo lo firma el candidato.
- Para preguntas con opciones, "value" debe ser EXACTAMENTE la etiqueta de una
  de las opciones (o una lista de etiquetas si la pregunta admite varias).
- Para texto corto, solo el dato.
- Para preguntas abiertas: 2 a 5 frases en primera persona, en el idioma del
  formulario, con hechos concretos del perfil. Sin frases de relleno.
- Si una pregunta trae "hint", es la respuesta que el propio candidato guardo
  para ese tema: usala como fuente principal.
- Responde SOLO un objeto JSON: {"answers": [{"key": "...", "status":
  "answered" | "unknown", "value": ...}]}
"""


def _facts_for_prompt(facts: dict[str, Any]) -> dict[str, Any]:
    """Sin correo ni telefono: el modelo no los necesita para nada."""
    return {k: v for k, v in facts.items() if k not in ("email", "phone")}


def _question_for_prompt(fd: FieldDraft, facts: dict[str, Any]) -> dict[str, Any]:
    pregunta: dict[str, Any] = {"key": fd.key, "label": fd.label, "type": fd.type, "required": fd.required}
    if fd.options:
        pregunta["options"] = [o["label"] for o in fd.options]
    pista = screening_for(facts, fd.topic)
    if pista:
        pregunta["hint"] = pista
    return pregunta


def _extract_json_object(raw: str) -> dict[str, Any]:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no hay un objeto JSON en la respuesta")
    parsed = json.loads(raw[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("la respuesta no es un objeto JSON")
    return parsed


def _ask_llm(draft: Draft, facts: dict[str, Any], pendientes: list[FieldDraft]) -> dict[str, dict[str, Any]]:
    """{key: respuesta}. Vacio si no hay IA o si falla: lo pendiente queda para
    el usuario, que es exactamente lo que pasaria sin agente."""
    from app.services.anthropic_client import (
        AI_MAX_TOKENS,
        LOW_EFFORT,
        get_anthropic_client,
        log_ai_failure,
        response_text,
    )

    client = get_anthropic_client()
    if client is None:
        return {}
    contenido = {
        "job": {"title": draft.title, "company": draft.company},
        "form_language": draft.language,
        "candidate_facts": _facts_for_prompt(facts),
        "questions": [_question_for_prompt(fd, facts) for fd in pendientes],
    }
    try:
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=AI_MAX_TOKENS,
            extra_body=LOW_EFFORT,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(contenido, ensure_ascii=False, default=str)}],
        )
        datos = _extract_json_object(response_text(response).strip())
    except Exception as exc:  # noqa: BLE001 - sin IA, lo pendiente pasa al usuario
        log_ai_failure("apply_agent", exc)
        return {}
    respuestas = {}
    for item in datos.get("answers") or []:
        if isinstance(item, dict) and item.get("key"):
            respuestas[str(item["key"])] = item
    return respuestas


def _apply_answer(fd: FieldDraft, answer: Optional[dict[str, Any]]) -> None:
    if not answer or answer.get("status") != "answered":
        return
    valor = answer.get("value")
    if fd.type == "select":
        etiqueta = valor[0] if isinstance(valor, list) and len(valor) == 1 else valor
        opcion = _option_by_label(fd.options, str(etiqueta or ""))
        if opcion:
            _set(fd, opcion["value"], opcion["label"], SOURCE_AI)
    elif fd.type == "multiselect":
        etiquetas = valor if isinstance(valor, list) else [valor]
        opciones = [_option_by_label(fd.options, str(e or "")) for e in etiquetas]
        # Todas validas o ninguna: medio conjunto de opciones es una respuesta
        # distinta de la que dio el modelo.
        if opciones and all(opciones):
            _set(fd, [o["value"] for o in opciones], ", ".join(o["label"] for o in opciones), SOURCE_AI)
    elif fd.type in _TEXT_LIMIT and isinstance(valor, (str, int, float)):
        texto = str(valor).strip()
        if texto:
            _set(fd, texto[: _TEXT_LIMIT[fd.type]], texto[: _TEXT_LIMIT[fd.type]], SOURCE_AI)


# ---------------------------------------------------------------- pasada 3

def _saved_topics(facts: dict[str, Any]) -> set[str]:
    return {s["topic"] for s in facts.get("screening") or [] if s.get("topic")}


def _finish(draft: Draft, saved_topics: set[str]) -> Draft:
    for fd in draft.fields:
        if fd.status == _PENDING:
            if draft.ai_policy and fd.kind in (KIND_OPEN, KIND_TEXT, KIND_CHOICE, KIND_SALARY, KIND_WORK_AUTH):
                _to_user(fd, "La empresa pide que respondas tú, sin IA.")
            elif fd.topic and fd.topic in saved_topics:
                _to_user(fd, "Tienes una respuesta guardada sobre esto: revísala y adáptala a esta pregunta.")
            elif fd.kind in (KIND_SALARY, KIND_WORK_AUTH) and not is_location_question(fd.label):
                _to_user(fd, "Guarda en tu perfil una respuesta sobre este tema y el agente la usará.")
            else:
                _to_user(fd, "Tu perfil no tiene datos para responder esto.")

    motivos: list[str] = []

    def add(code: str) -> None:
        if code not in motivos:
            motivos.append(code)

    if draft.ai_policy:
        add("ai_policy")
    for fd in draft.fields:
        if fd.kind == KIND_CONSENT and fd.required:
            add("consent")
        if fd.kind == KIND_SENSITIVE and fd.required:
            add("sensitive")
        if fd.kind == KIND_PERSONAL and fd.required:
            add("personal")
        if fd.kind == KIND_SALARY and (fd.required or fd.status == FILLED):
            add("salary")
        if fd.kind == KIND_WORK_AUTH and (fd.required or fd.status == FILLED):
            add("work_auth")
        if fd.kind == KIND_OPEN and fd.source == SOURCE_AI:
            add("open_text")
        if fd.required and fd.status == NEEDS_USER:
            add("needs_user")
    if draft.education_required:
        add("education")

    draft.review_reasons = motivos
    draft.auto_eligible = not motivos
    return draft


# ---------------------------------------------------------------- entrada

def build_deterministic(form: ApplicationForm, facts: dict[str, Any]) -> Draft:
    """Pasadas 1 y 3, sin red ni IA. Lo que quede pendiente pasa al usuario."""
    draft = _start(form, facts)
    return _finish(draft, _saved_topics(facts))


def _start(form: ApplicationForm, facts: dict[str, Any]) -> Draft:
    ai_policy = any(mentions_ai_policy(f.label, f.description) for f in form.fields)
    campos = []
    for field in form.fields:
        fd = FieldDraft(
            key=field.key,
            label=field.label,
            type=field.type,
            required=field.required,
            section=field.section,
            kind=classify(field),
            options=list(field.options),
            topic=topic_of(field.label),
            alternatives=list(field.alternatives),
        )
        _deterministic(fd, field, facts, ai_policy)
        campos.append(fd)
    return Draft(
        ats=form.ats,
        board=form.board,
        job_id=form.job_id,
        url=form.url,
        form_url=form.form_url,
        title=form.title,
        company=form.company,
        language=form.language,
        ai_policy=ai_policy,
        fields=campos,
        notices=list(form.notices),
        education_required=form.education_required,
    )


def _llm_may_answer(fd: FieldDraft, facts: dict[str, Any]) -> bool:
    """Que preguntas puede intentar el LLM.

    Salario, autorizacion y patrocinio: solo si el usuario guardo una
    respuesta sobre ese tema. En el banco de prueba, sin respuesta guardada, el
    modelo contestaba "No" a "¿necesitas patrocinio?" -- una declaracion
    migratoria inventada. Pais, zona horaria y ubicacion si se deducen del
    perfil."""
    if fd.status != _PENDING:
        return False
    if fd.kind in (KIND_CHOICE, KIND_TEXT, KIND_OPEN):
        return True
    if fd.kind in (KIND_SALARY, KIND_WORK_AUTH):
        return bool(screening_for(facts, fd.topic)) or (fd.kind == KIND_WORK_AUTH and is_location_question(fd.label))
    return False


async def build_draft(form: ApplicationForm, facts: dict[str, Any], *, use_ai: bool = True) -> Draft:
    draft = _start(form, facts)
    pendientes = [fd for fd in draft.fields if _llm_may_answer(fd, facts)]
    if use_ai and pendientes and not draft.ai_policy:
        respuestas = await asyncio.to_thread(_ask_llm, draft, facts, pendientes)
        for fd in pendientes:
            _apply_answer(fd, respuestas.get(fd.key))
        draft.used_ai = bool(respuestas)
    return _finish(draft, _saved_topics(facts))
