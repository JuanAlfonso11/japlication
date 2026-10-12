"""Que clase de pregunta es cada campo del formulario.

La clase decide quien puede responder:

  identity   -- datos de contacto: los pone el perfil.
  document   -- CV y carta: archivos.
  consent    -- declaraciones y consentimientos ("I agree", "I confirm",
                avisos de privacidad). SOLO el usuario: es su firma.
  sensitive  -- diversidad, salud, nacionalidad, edad, antecedentes. El agente
                nunca las responde; si son voluntarias se dejan en blanco.
  personal   -- hechos de la vida del usuario que el perfil no registra: si ya
                trabajo o se postulo en esa empresa, si es o es pariente de un
                funcionario, quien lo refirio, acuerdos con su empleador, su
                usuario en otra plataforma. Nunca las responde el agente: en el
                banco de prueba el LLM contestaba "No" a todas, y que el perfil
                no diga algo no significa que sea falso.
  salary     -- expectativa salarial: se puede proponer desde el perfil, pero
                siempre la revisa el usuario.
  work_auth  -- autorizacion de trabajo, visa, pais, reubicacion: igual.
  open_text  -- preguntas abiertas (textarea).
  choice     -- cualquier otra pregunta con opciones.
  text       -- cualquier otra pregunta de texto corto.

El orden de las comprobaciones importa: "Please confirm that you have read
our Privacy Notice" es un consentimiento antes que cualquier otra cosa, y
"Which gender do you identify as?" es sensible aunque sea un desplegable.

Todo se compara sin acentos y en minusculas, para que las mismas expresiones
sirvan para las preguntas del formulario (casi siempre en ingles) y para las
respuestas guardadas del perfil (en espanol).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from app.services.apply_agent.greenhouse import FormField

KIND_IDENTITY = "identity"
KIND_DOCUMENT = "document"
KIND_CONSENT = "consent"
KIND_SENSITIVE = "sensitive"
KIND_PERSONAL = "personal"
KIND_SALARY = "salary"
KIND_WORK_AUTH = "work_auth"
KIND_OPEN = "open_text"
KIND_CHOICE = "choice"
KIND_TEXT = "text"


def norm(text: Optional[str]) -> str:
    sin_acentos = unicodedata.normalize("NFKD", text or "")
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


_CONSENT = re.compile(
    r"\b(i agree|agree to|agree with|i acknowledge|acknowledg\w*|consent\w*|i certify|certify that|"
    r"i confirm|confirm that|i have read|read and (understood|agree\w*)|privacy (notice|policy|statement)|"
    r"terms (and|&) conditions|i declare|attest\w*|i understand that|own words|gdpr|arbitrat\w*|agreement|"
    r"please note|will not be considered)\b"
)

_PERSONAL = re.compile(
    r"(\b(previously|ever|before|in the past|prior)\b.{0,60}\b(work\w*|employ\w*|consult\w*|appl\w*|"
    r"interview\w*|contract\w*)\b"
    r"|\b(work\w*|employ\w*|consult\w*|appl\w*|interview\w*)\b.{0,40}\b(before|previously|in the past)\b"
    r"|government official|public official|politically exposed|close relative|family member|"
    r"related to (any|an|a|someone)|referred (to this position )?by|referral|conflict of interest|"
    r"financial interest|non-?compete|post-employment|employment agreements?|current manager|"
    r"\buser ?name\b)"
)

_SENSITIVE = re.compile(
    r"\b(gender|pronouns?|sex|sexual orientation|lgbt\w*|transgender|race|racial|ethnic\w*|hispanic|"
    r"latin[oax]|veteran|disabilit\w*|disabled|religio\w*|nationalit\w*|date of birth|birth ?date|age|"
    r"how old|marital|pregnan\w*|health|medical|criminal|convict\w*|felony|caste)\b"
)

_SALARY = re.compile(
    r"\b(salary|salaries|compensation|pay expectations?|expected pay|desired pay|hourly rate|day rate|"
    r"rate expectations?|remuneraci\w*|sueldo|salarial|ote)\b"
)

_WORK_AUTH = re.compile(
    r"(authori[sz]ed to work|work authori[sz]ation|right to work|legally (authori[sz]ed|eligible|able) to work|"
    r"eligib\w* to work|\bsponsor\w*|\bvisas?\b|work permit|green card|citizenship|\bcitizen\b|relocat\w*|"
    r"\bcountry\b|"
    r"where (are you|do you) (currently )?(live|reside|based|located)|time ?zone)"
)

#: (clave del perfil, expresion). La clave la entiende facts.py.
_IDENTITY_LABELS: list[tuple[str, re.Pattern[str]]] = [
    ("linkedin", re.compile(r"\blinked ?in\b")),
    ("github", re.compile(r"\bgithub\b")),
    ("website", re.compile(r"\b(website|portfolio|personal (site|page)|blog)\b")),
    ("current_company", re.compile(r"\b(current|most recent) (company|employer)\b")),
    ("current_title", re.compile(r"\b(current|most recent) (job )?(title|role|position)\b")),
    ("full_name", re.compile(r"^(full |legal )?name\??$")),
    ("location", re.compile(r"^(city|location|current location|location \(city\)|city, country)\??$")),
]

_IDENTITY_KEYS = {"first_name", "last_name", "email", "phone", "preferred_name", "location"}

#: Una politica del empleador contra contenido generado con IA. Canonical:
#: "I agree to use only my own words... the use of AI or other generated
#: content will disqualify my application". Anthropic: "AI Policy for
#: Application". Si aparece, el LLM no redacta nada en ese formulario.
_AI_POLICY = re.compile(
    r"(own words.{0,240}\b(ai|artificial intelligence|generated)\b"
    r"|\b(ai|artificial intelligence|chatgpt|llms?|generative ai|genai)\b.{0,120}"
    r"\b(polic(y|ies)|prohibit\w*|not (be )?(used|permitted|allowed)|disqualif\w*|guidelines|"
    r"without (the )?(use|help|assistance))"
    r"|\buse of (ai|artificial intelligence)\b.{0,80}\b(disqualif\w*|prohibit\w*|not (permitted|allowed)))"
)

#: Temas de las preguntas que se repiten de un formulario a otro. Sirven para
#: emparejar una pregunta del formulario con una respuesta guardada en el
#: perfil aunque esten redactadas distinto, y en idiomas distintos. El orden
#: importa: "Will you require visa sponsorship?" es patrocinio, no autorizacion.
TOPICS: list[tuple[str, re.Pattern[str]]] = [
    ("sponsorship", re.compile(r"\b(sponsor\w*|patrocin\w*|visas?)\b")),
    ("work_auth", re.compile(r"(authori[sz]\w*|autoriza\w*|right to work|eligib\w* to work|legally)")),
    ("salary", _SALARY),
    (
        "start_date",
        re.compile(
            r"(start date|notice period|when can you start|available to start|earliest start|"
            r"\bavailability\b|disponibilidad|preaviso|incorpora\w*|comenzar)"
        ),
    ),
    ("work_mode", re.compile(r"\b(remote\w*|hybrid|on-?site|in[- ]office|remoto|hibrid\w*|presencial)\b")),
    ("years_experience", re.compile(r"(years? of (\w+ ){0,3}experience|anos de experiencia)")),
    (
        "motivation",
        re.compile(
            r"(why (do you want|are you interested|would you like|.{0,40}\binterest)|what (excites|interests) you|"
            r"por que te interesa|te motiva)"
        ),
    ),
]


_SENTENCE_END = re.compile(r"(?<=[.?!])\s+")


def question_core(label: Optional[str]) -> str:
    """La pregunta de verdad dentro de una etiqueta larga.

    Canonical pregunta: "We require all colleagues to meet in person 2-4
    times a year... will likely require international travel and entry
    requirement visas and vaccinations. Are you willing and able to commit to
    this?". Buscando el tema en toda la etiqueta, "visas" la convertia en una
    pregunta de patrocinio, y el "Si" guardado para "¿Requieres patrocinio de
    visa?" acababa contestando otra cosa. El tema sale de la ultima frase con
    signo de interrogacion; si no hay ninguna, de la etiqueta entera.
    """
    texto = (label or "").strip()
    if len(texto) <= 120:
        return texto
    frases = [f.strip() for f in _SENTENCE_END.split(texto) if f.strip()]
    preguntas = [f for f in frases if f.endswith("?")]
    return preguntas[-1] if preguntas else texto


def topic_of(text: Optional[str]) -> Optional[str]:
    texto = norm(question_core(text))
    for nombre, expresion in TOPICS:
        if expresion.search(texto):
            return nombre
    return None


_LOCATION_QUESTION = re.compile(r"\b(country|time ?zone|located|location|reside|residence|based|address)\b")


def is_location_question(label: Optional[str]) -> bool:
    """Pais, zona horaria, donde vive: se deduce de la ubicacion del perfil,
    a diferencia de la autorizacion de trabajo o el patrocinio, que no."""
    return bool(_LOCATION_QUESTION.search(norm(question_core(label))))


def mentions_ai_policy(*texts: Optional[str]) -> bool:
    return bool(_AI_POLICY.search(norm(" ".join(t for t in texts if t))))


#: Una etiqueta de identidad es corta: "LinkedIn Profile URL", "Website". Mas
#: larga ya es una pregunta que solo menciona el dato -- GitLab pregunta "Are
#: you subject to any employment agreements... with your current employer?",
#: y por decir "current employer" se llenaba con el nombre de la empresa.
_IDENTITY_MAX_LABEL = 60


def identity_key(field: FormField) -> Optional[str]:
    if field.key in _IDENTITY_KEYS:
        return field.key
    etiqueta = norm(field.label)
    if len(etiqueta) > _IDENTITY_MAX_LABEL:
        return "location" if field.section == "location" else None
    for clave, expresion in _IDENTITY_LABELS:
        if expresion.search(etiqueta):
            return clave
    if field.section == "location":
        return "location"
    return None


def classify(field: FormField) -> str:
    # Consentimiento y sensibles miran la etiqueta entera: un "I agree" o un
    # "gender" en cualquier parte basta para no contestar. Salario y
    # autorizacion miran solo la pregunta (ver question_core).
    etiqueta = norm(field.label)
    pregunta = norm(question_core(field.label))
    if field.section in ("compliance", "demographic"):
        return KIND_SENSITIVE
    if field.type == "file" or field.key in ("resume", "cover_letter"):
        return KIND_DOCUMENT
    if _CONSENT.search(etiqueta):
        return KIND_CONSENT
    if _SENSITIVE.search(etiqueta):
        return KIND_SENSITIVE
    if _PERSONAL.search(pregunta):
        return KIND_PERSONAL
    if identity_key(field):
        return KIND_IDENTITY
    if _SALARY.search(pregunta):
        return KIND_SALARY
    if _WORK_AUTH.search(pregunta):
        return KIND_WORK_AUTH
    if field.type == "textarea":
        return KIND_OPEN
    if field.type in ("select", "multiselect"):
        return KIND_CHOICE
    return KIND_TEXT
