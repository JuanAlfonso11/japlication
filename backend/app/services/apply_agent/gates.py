"""Puertas antes de aplicar: lo que descarta una oferta por mucho que encaje.

Viene del marco de evaluacion de ai-job-search
(.claude/skills/job-application-assistant/04-job-evaluation.md, "Eligibility
Gate" y "Language Gate"), adaptado a JobPilot:

  * Elegibilidad. Si la oferta exige permiso de trabajo en un pais que no es el
    del perfil, o ciudadania / habilitacion de seguridad, no se envia sola. Lo
    detecta work_authorization.py (la misma heuristica que pinta el aviso de la
    tarjeta). "El silencio no es permiso": si la oferta no dice nada, pasa,
    pero el formulario puede preguntarlo y esa respuesta la da el usuario.
  * Idioma. Si exige como condicion del puesto un idioma que el perfil no
    tiene, FAIL. Si el perfil lo tiene pero a un nivel que parece menor que el
    que pide ("fluent" contra "intermedio"), FLAG: se prepara igual y se avisa,
    porque "fluent" varia mucho entre empresas y el usuario decide.
  * Cerrada o vencida: no se envia nada a una oferta que ya no existe.

Nada de esto impide PREPARAR la aplicacion: el swipe fue una decision del
usuario y la respeta. Lo que hacen es frenar el envio automatico y decir por
que, citando la frase de la oferta, para que el usuario juzgue con el texto
delante (el puede saber algo de su situacion que el perfil no registra).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Iterable, Optional

from app.services import work_authorization

BLOCK = "block"  # frena el envio automatico
WARN = "warn"    # solo avisa


@dataclass
class Gate:
    code: str
    level: str
    message: str
    #: La frase de la oferta que lo dispara, tal cual (recortada).
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fold(text: Optional[str]) -> str:
    sin_tildes = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in sin_tildes if not unicodedata.combining(c)).lower()


# ------------------------------------------------------------------ idioma

#: Idioma -> como se escribe en ingles y en espanol (sin tildes, minusculas).
_LANGUAGES: dict[str, tuple[str, ...]] = {
    "english": ("english", "ingles"),
    "spanish": ("spanish", "espanol", "castellano"),
    "portuguese": ("portuguese", "portugues"),
    "french": ("french", "frances"),
    "german": ("german", "aleman"),
    "italian": ("italian", "italiano"),
    "dutch": ("dutch", "neerlandes", "holandes"),
    "polish": ("polish", "polaco"),
    "russian": ("russian", "ruso"),
    "ukrainian": ("ukrainian", "ucraniano"),
    "turkish": ("turkish", "turco"),
    "arabic": ("arabic", "arabe"),
    "hebrew": ("hebrew", "hebreo"),
    "hindi": ("hindi",),
    "japanese": ("japanese", "japones"),
    "korean": ("korean", "coreano"),
    "chinese": ("chinese", "mandarin", "cantonese", "chino", "mandarin"),
    "swedish": ("swedish", "sueco"),
    "danish": ("danish", "danes"),
    "norwegian": ("norwegian", "noruego"),
    "finnish": ("finnish", "finlandes"),
    "czech": ("czech", "checo"),
    "greek": ("greek", "griego"),
    "romanian": ("romanian", "rumano"),
    "hungarian": ("hungarian", "hungaro"),
}
_ALIAS_TO_LANG = {alias: lang for lang, aliases in _LANGUAGES.items() for alias in aliases}
_LANG_ALT = "|".join(sorted((re.escape(a) for a in _ALIAS_TO_LANG), key=len, reverse=True))

#: Niveles que se piden, de menos a mas. Lo que no se reconoce no cuenta.
_LEVEL_WORDS = {
    1: ("basic", "basico", "a1", "a2", "elementary", "conversational", "conversacional"),
    2: ("intermediate", "intermedio", "b1", "working", "professional working", "good", "buen"),
    3: ("advanced", "avanzado", "b2", "c1", "business", "proficient", "strong", "excellent", "excelente",
        "full professional", "profesional", "high"),
    4: ("fluent", "fluency", "fluido", "fluidez", "c2", "native", "nativo", "bilingual", "bilingue", "mother tongue"),
}
_LEVEL_ALT = "|".join(
    sorted((re.escape(w) for words in _LEVEL_WORDS.values() for w in words), key=len, reverse=True)
)

#: "fluent in German", "German (fluent)", "C1 German", "native-level Japanese",
#: "dominio del aleman". Solo cuenta si va unido a un nivel o a un verbo de
#: exigencia: "our German office" no pide aleman.
_REQ_LEVEL_BEFORE = re.compile(
    rf"\b(?P<level>{_LEVEL_ALT})(?:[\s-]+level)?(?:\s+(?:in|en|de|written and spoken|spoken and written|verbal and written))?"
    rf"\s+(?P<lang>{_LANG_ALT})\b"
)
_REQ_LEVEL_AFTER = re.compile(
    rf"\b(?P<lang>{_LANG_ALT})\s*(?:\(|-|:|,)?\s*(?:at\s+(?:a\s+)?)?(?:language\s+)?(?:skills?\s+)?(?:\(\s*)?"
    rf"(?P<level>{_LEVEL_ALT})\b"
)
_REQ_VERB = re.compile(
    rf"\b(?:speak|speaks|speaking|must\s+speak|communicate\s+in|dominio\s+(?:del|de)|hablar)\s+(?P<lang>{_LANG_ALT})\b"
)
#: "German is a plus" / "nice to have" no es un requisito.
_OPTIONAL_AFTER = re.compile(r"^[^.;,\n]{0,40}?\b(plus|bonus|nice to have|advantage|preferred|deseable|valorable|ventaja)")


def _level_of(word: str) -> int:
    word = _fold(word).strip()
    for nivel, palabras in _LEVEL_WORDS.items():
        if word in palabras:
            return nivel
    return 0


def required_languages(description: Optional[str]) -> dict[str, tuple[int, str]]:
    """Idiomas que la oferta pide como condicion del puesto: {idioma: (nivel, frase)}.

    Nivel 0 = lo pide sin decir nivel. El idioma en que esta escrita la oferta
    NO cuenta: una oferta en ingles no exige ingles por estar en ingles."""
    texto = _fold(description)
    pedidos: dict[str, tuple[int, str]] = {}
    for patron in (_REQ_LEVEL_BEFORE, _REQ_LEVEL_AFTER, _REQ_VERB):
        for m in patron.finditer(texto):
            if _OPTIONAL_AFTER.match(texto[m.end():]):
                continue
            idioma = _ALIAS_TO_LANG[m.group("lang")]
            nivel = _level_of(m.groupdict().get("level") or "")
            frase = texto[max(0, m.start() - 30): m.end() + 30].strip()
            if idioma not in pedidos or nivel > pedidos[idioma][0]:
                pedidos[idioma] = (nivel, frase)
    return pedidos


def _profile_languages(languages: Iterable[Any]) -> dict[str, int]:
    """{idioma: nivel} del perfil. Un idioma sin nivel reconocible cuenta como
    intermedio: el usuario lo declaro y no se le resta mas de la cuenta."""
    salida: dict[str, int] = {}
    for item in languages or []:
        nombre = item.get("name") if isinstance(item, dict) else str(item)
        nivel_txt = item.get("level") if isinstance(item, dict) else ""
        idioma = None
        for palabra in re.findall(r"[a-z]+", _fold(nombre)):
            if palabra in _ALIAS_TO_LANG:
                idioma = _ALIAS_TO_LANG[palabra]
                break
        if not idioma:
            continue
        nivel = 0
        for palabra in re.findall(r"[a-z0-9]+", _fold(nivel_txt)):
            nivel = max(nivel, _level_of(palabra))
        salida[idioma] = max(salida.get(idioma, 0), nivel or 2)
    return salida


_NOMBRE = {
    "english": "inglés", "spanish": "español", "portuguese": "portugués", "french": "francés",
    "german": "alemán", "italian": "italiano", "dutch": "neerlandés", "polish": "polaco",
    "russian": "ruso", "ukrainian": "ucraniano", "turkish": "turco", "arabic": "árabe",
    "hebrew": "hebreo", "hindi": "hindi", "japanese": "japonés", "korean": "coreano",
    "chinese": "chino", "swedish": "sueco", "danish": "danés", "norwegian": "noruego",
    "finnish": "finlandés", "czech": "checo", "greek": "griego", "romanian": "rumano",
    "hungarian": "húngaro",
}


def language_gates(description: Optional[str], profile_languages: Iterable[Any]) -> list[Gate]:
    tiene = _profile_languages(profile_languages)
    puertas = []
    for idioma, (nivel, frase) in required_languages(description).items():
        nombre = _NOMBRE.get(idioma, idioma)
        if idioma not in tiene:
            # Sin idiomas en el perfil no se puede saber: se avisa, no se frena.
            if not tiene:
                puertas.append(Gate("language_unknown", WARN,
                                    f"La oferta pide {nombre} y tu perfil no dice qué idiomas hablas.", [frase]))
            else:
                puertas.append(Gate("language", BLOCK,
                                    f"La oferta exige {nombre} y no está entre tus idiomas.", [frase]))
        elif nivel and nivel > tiene[idioma]:
            puertas.append(Gate("language_level", WARN,
                                f"La oferta pide un {nombre} de nivel más alto que el que declaras. "
                                "Decide tú si te alcanza.", [frase]))
    return puertas


# ------------------------------------------------------------------ elegibilidad

_CLEARANCE = re.compile(
    r"security\s+clearance|active\s+(?:secret|top\s+secret|ts/sci)\b|\bts/sci\b"
    r"|(?:must|need\s+to|required\s+to)\s+be\s+(?:a\s+)?(?:u\.s\.\s+|us\s+|uk\s+|eu\s+)?citizen"
    r"|citizenship\s+(?:is\s+)?required|permanent\s+residen(?:t|cy)\s+(?:is\s+)?required"
    r"|green\s+card\s+holder",
    re.IGNORECASE,
)


def eligibility_gates(description: Optional[str], location: Optional[str], user_country: Optional[str]) -> list[Gate]:
    puertas = []
    m = _CLEARANCE.search(description or "")
    if m:
        frase = (description or "")[max(0, m.start() - 40): m.end() + 40].strip()
        puertas.append(Gate("citizenship", BLOCK,
                            "La oferta pide ciudadanía, residencia permanente o una habilitación de seguridad.",
                            [frase]))
    auth = work_authorization.detect(description, location)
    if auth.blocks(user_country):
        puertas.append(Gate("work_permit", BLOCK,
                            f"{auth.label}: tu perfil dice que estás en otro país.",
                            [e[:160] for e in auth.evidence[:2]]))
    elif auth.restricted and user_country is None:
        puertas.append(Gate("work_permit_unknown", WARN,
                            f"{auth.label}. Pon tu país en el perfil para saber si te aplica.",
                            [e[:160] for e in auth.evidence[:2]]))
    return puertas


# ------------------------------------------------------------------ todo junto

def evaluate(job: Any, profile: Any, user_country: Optional[str], today: Optional[date] = None) -> list[Gate]:
    """Todas las puertas de una oferta para un perfil."""
    today = today or date.today()
    puertas: list[Gate] = []
    if getattr(job, "closed_at", None) is not None:
        puertas.append(Gate("closed", BLOCK, "La oferta ya está cerrada en su origen."))
    deadline = getattr(job, "deadline", None)
    if deadline is not None and deadline < today:
        puertas.append(Gate("deadline", BLOCK, f"El plazo de la oferta venció el {deadline:%d/%m/%Y}."))
    descripcion = getattr(job, "description", None)
    puertas += eligibility_gates(descripcion, getattr(job, "location", None), user_country)
    puertas += language_gates(descripcion, getattr(profile, "languages", None) or [])
    return puertas


def blocking(puertas: Iterable[Gate]) -> list[Gate]:
    return [p for p in puertas if p.level == BLOCK]
