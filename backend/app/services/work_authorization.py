"""Ofertas que exigen permiso de trabajo en un pais concreto.

Por que existe
--------------
El escaner de ATS (ats_boards.py) trajo decenas de ofertas "Remote - United
States": remotas, si, pero casi siempre solo para quien ya puede trabajar
legalmente en EE. UU. Para alguien en Republica Dominicana son swipes
perdidos, y el porcentaje de match no lo reflejaba porque solo mira
habilidades y experiencia.

La idea viene de career-ops (github.com/career-ops-hq/career-ops, MIT), que
separa los "bloqueos" -- lo que descarta una oferta por mucho que encajen las
habilidades -- del resto de la puntuacion.

Que se mira
-----------
  * La ubicacion: "Remote - US", "USA Only", "Remote · Canada". Si dice
    "Anywhere"/"Worldwide", no hay restriccion por ubicacion.
  * La descripcion, que manda sobre la ubicacion: "must be authorized to
    work in the United States", "US citizenship required", "we are unable
    to sponsor visas", "must be based in the UK".

Es heuristica y lo dice: la etiqueta describe lo que la oferta PIDE, no una
conclusion legal. Si la ubicacion o la descripcion no nombran ningun pais,
no se inventa uno.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

# ------------------------------------------------------------ regiones
# (codigo, nombre para mostrar, patron sin distinguir mayusculas, patron
# que SI las distingue). "US" solo en mayusculas: en minusculas es "us" de
# "join us", que aparece en casi todas las descripciones.
_REGIONS: tuple[tuple[str, str, str, Optional[str]], ...] = (
    ("US", "EE. UU.", r"united states|\busa\b|estados unidos|\bee\.?\s?uu\b", r"\bUS\b|(?<![A-Za-z])U\.S\b\.?(?:A\b\.?)?"),
    ("CA", "Canadá", r"\bcanad[aá]\b", None),
    ("UK", "Reino Unido", r"united kingdom|\buk\b|great britain|\bengland\b|reino unido|\blondon\b", None),
    ("EU", "la UE", r"\beu\b|european union|uni[oó]n europea|\beea\b", None),
    ("EUROPE", "Europa", r"\beurope\b|\beuropa\b", None),
    ("EMEA", "EMEA", r"\bemea\b", None),
    ("APAC", "Asia-Pacífico", r"\bapac\b|asia[\s-]pacific", None),
    ("LATAM", "Latinoamérica", r"\blatam\b|latin america|latinoam[eé]rica|am[eé]rica latina|south america|"
                                r"sudam[eé]rica|central america|centroam[eé]rica|caribbean|\bcaribe\b", None),
    ("NA", "Norteamérica", r"north america|norte\s?am[eé]rica", None),
    ("AMERICAS", "América", r"\bam[eé]ricas\b", None),
    ("DE", "Alemania", r"\bgermany\b|\balemania\b|deutschland|\bberlin\b|\bmunich\b", None),
    ("FR", "Francia", r"\bfrance\b|\bfrancia\b|\bparis\b", None),
    ("ES", "España", r"\bspain\b|espa[nñ]a\b|\bmadrid\b|\bbarcelona\b", None),
    ("NL", "Países Bajos", r"netherlands|pa[ií]ses bajos|\bholanda\b|amsterdam", None),
    ("IE", "Irlanda", r"\bireland\b|\birlanda\b|\bdublin\b", None),
    ("PT", "Portugal", r"\bportugal\b|\blisbon\b|\blisboa\b", None),
    ("PL", "Polonia", r"\bpoland\b|\bpolonia\b", None),
    ("IL", "Israel", r"\bisrael\b|tel aviv", None),
    ("IN", "India", r"\bindia\b|bangalore|bengaluru", None),
    ("AU", "Australia", r"\baustralia\b|\bsydney\b|\bmelbourne\b", None),
    ("SG", "Singapur", r"singapore|singapur", None),
    ("JP", "Japón", r"\bjapan\b|jap[oó]n\b|\btokyo\b", None),
    ("PH", "Filipinas", r"philippines|filipinas", None),
    ("MX", "México", r"\bm[eé]xico\b", None),
    ("BR", "Brasil", r"\bbrazil\b|\bbrasil\b|s[aã]o paulo", None),
    ("AR", "Argentina", r"\bargentina\b|buenos aires", None),
    ("CO", "Colombia", r"\bcolombia\b|\bbogot[aá]\b|medell[ií]n", None),
    ("CL", "Chile", r"\bchile\b|\bsantiago\b(?! de los caballeros)", None),
    ("PE", "Perú", r"\bper[uú]\b|\blima\b", None),
    ("CR", "Costa Rica", r"costa rica", None),
    ("DO", "República Dominicana", r"dominican republic|rep[uú]blica dominicana|santo domingo|santiago de los caballeros", None),
)

_NAMES = {code: name for code, name, _, _ in _REGIONS}
_COMPILED = [
    (code, re.compile(ci, re.IGNORECASE), re.compile(cs) if cs else None)
    for code, _, ci, cs in _REGIONS
]

_EUROPE = {"DE", "FR", "ES", "NL", "IE", "PT", "PL", "UK"}
_EU = _EUROPE - {"UK"}
_LATAM = {"MX", "BR", "AR", "CO", "CL", "PE", "CR", "DO"}

#: A que regiones pertenece cada pais: alguien en DO cabe en "LATAM" y en
#: "Americas", no en "EMEA".
_MEMBERSHIP: dict[str, set[str]] = {}
for _code in _NAMES:
    _MEMBERSHIP[_code] = {_code}
for _c in _EUROPE:
    _MEMBERSHIP[_c] |= {"EUROPE", "EMEA"}
for _c in _EU:
    _MEMBERSHIP[_c].add("EU")
for _c in ("IL",):
    _MEMBERSHIP[_c].add("EMEA")
for _c in _LATAM:
    _MEMBERSHIP[_c] |= {"LATAM", "AMERICAS"}
for _c in ("US", "CA"):
    _MEMBERSHIP[_c] |= {"AMERICAS", "NA"}
_MEMBERSHIP["MX"].add("NA")
for _c in ("IN", "AU", "SG", "JP", "PH"):
    _MEMBERSHIP[_c].add("APAC")
# Una ruta "LATAM" dice que en esa lista cabe el pais; "Americas" tambien.
# Ninguno de los grupos es un pais, asi que un grupo no "pertenece" a nada.

_GLOBAL_RE = re.compile(
    r"\b(anywhere|worldwide|global(ly)?|any location|international|todo el mundo|cualquier (lugar|pa[ií]s))\b",
    re.IGNORECASE,
)

# ------------------------------------------------------------ descripcion
_PLACE_WINDOW = 60

#: Frases que atan la oferta a un pais. El pais va DESPUES de la frase y se
#: busca en una ventana corta, para no tomar uno de otra parte del texto.
_AUTH_LEADS = re.compile(
    r"(?:legally\s+)?(?:authori[sz]ed|eligible|permitted|able)\s+to\s+(?:legally\s+)?work\s+(?:in|within|from|for)\s+"
    r"|work\s+authori[sz]ation\s+(?:in|for)\s+"
    r"|right\s+to\s+work\s+in\s+"
    r"|must\s+(?:currently\s+)?(?:be\s+)?(?:located|based|reside|residing|live|living|resident)\s+(?:in|within)\s+"
    r"|(?:only\s+)?(?:open|available)\s+(?:only\s+)?to\s+(?:candidates|applicants|residents|people)\s+"
    r"(?:who\s+(?:are|live)\s+)?(?:located\s+|based\s+|residing\s+)?(?:in|of|within)\s+"
    r"|permiso\s+de\s+trabajo\s+(?:en|para)\s+"
    r"|(?:residir|vivir|estar\s+ubicad[oa])\s+en\s+",
    re.IGNORECASE,
)
#: "must be located in a US time zone" habla de horario, no de permiso.
_TIMEZONE_AFTER = re.compile(r"^[^.;\n]{0,25}?(time\s?zones?|hours|horario)", re.IGNORECASE)

_CITIZEN_US = re.compile(
    r"(?:U\.S\.|US|United States)\s+citizen(?:ship)?\b|security\s+clearance|green\s+card\s+holder",
    re.IGNORECASE,
)
_ONLY_AFTER = re.compile(
    r"(?P<place>\bUS\b|U\.S\.|\bUSA\b|United States|\bUK\b|Canada|Europe|\bEU\b|LATAM)\s*"
    r"(?:-|–|\()?\s*(?:based\s+)?(?:candidates\s+|residents\s+|citizens\s+)?only\b",
    re.IGNORECASE,
)

_NO_SPONSOR = re.compile(
    r"(?:not|unable\s+to|cannot|can't|can\s+not|won't|will\s+not|do\s+not|does\s+not|don't|doesn't|"
    r"are\s+not\s+able\s+to|is\s+not\s+able\s+to)\s+(?:currently\s+|presently\s+)?"
    r"(?:offer|provide|support|sponsor)\w*\s+(?:any\s+|future\s+|new\s+)?(?:(?:h-?1b|visa|employment|work)\s+)*"
    r"(?:sponsorship|visas?)"
    r"|(?:not|unable\s+to|cannot|won't|will\s+not|do\s+not|does\s+not)\s+sponsor\b"
    r"|without\s+(?:the\s+need\s+for\s+)?(?:current\s+or\s+future\s+|future\s+|any\s+)?"
    r"(?:(?:visa|employment|work)\s+)*sponsorship"
    r"|\bno\s+(?:visa\s+)?sponsorship"
    r"|sponsorship\s+(?:is\s+)?not\s+(?:available|offered|provided|possible)"
    r"|no\s+(?:ofrecemos|patrocinamos|se\s+ofrece|podemos\s+ofrecer)\s+(?:patrocinio|visa)",
    re.IGNORECASE,
)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def regions_in(text: str) -> list[str]:
    """Codigos de pais/region que nombra `text`, en orden de aparicion."""
    if not text:
        return []
    hallados: list[tuple[int, str]] = []
    for code, ci, cs in _COMPILED:
        m = ci.search(text) or ci.search(_strip_accents(text))
        pos = m.start() if m else None
        if cs is not None:
            m2 = cs.search(text)
            if m2 and (pos is None or m2.start() < pos):
                pos = m2.start()
        if pos is not None:
            hallados.append((pos, code))
    return [code for _, code in sorted(hallados)]


def country_code(value: Optional[str]) -> Optional[str]:
    """El pais del perfil ("República Dominicana", "Santo Domingo, DO") a codigo."""
    if not value:
        return None
    for code in regions_in(value):
        if len(code) == 2:  # un pais, no un grupo como LATAM o EMEA
            return code
    return None


@dataclass(frozen=True)
class WorkAuth:
    #: Donde exige la oferta poder trabajar. Vacio = no lo dice.
    regions: tuple[str, ...] = ()
    #: La descripcion lo dice con todas las letras (no solo la ubicacion).
    explicit: bool = False
    no_sponsorship: bool = False
    evidence: list[str] = field(default_factory=list, compare=False)

    @property
    def restricted(self) -> bool:
        return bool(self.regions) or self.no_sponsorship

    def region_names(self) -> str:
        nombres = [_NAMES.get(r, r) for r in self.regions[:3]]
        return ", ".join(nombres) + ("…" if len(self.regions) > 3 else "")

    @property
    def label(self) -> Optional[str]:
        if not self.restricted:
            return None
        partes = []
        if self.regions:
            if self.explicit:
                partes.append(f"Exige permiso de trabajo en {self.region_names()}")
            else:
                partes.append(f"Solo candidatos en {self.region_names()}")
        if self.no_sponsorship:
            partes.append("sin patrocinio de visa" if partes else "No patrocina visa")
        return " · ".join(partes)

    def blocks(self, user_country: Optional[str]) -> Optional[bool]:
        """True si la oferta deja fuera a alguien de `user_country`.

        None cuando no se puede saber: el perfil no dice el pais, o la oferta
        no nombra ninguno (un "no patrocinamos visa" sin pais no dice si una
        persona en remoto desde otro pais la necesita).
        """
        if not self.regions or not user_country:
            return None
        suyas = _MEMBERSHIP.get(user_country, {user_country})
        return not (set(self.regions) & suyas)


def _place_after(text: str, end: int) -> list[str]:
    ventana = text[end : end + _PLACE_WINDOW]
    if _TIMEZONE_AFTER.search(ventana):
        return []
    # Hasta el primer punto o salto de linea: "work in the US. We are also
    # hiring in Canada" no convierte a Canada en requisito.
    ventana = re.split(r"[.;\n](?!S\.|A\.)", ventana, maxsplit=1)[0]
    return regions_in(ventana)


def detect(description: Optional[str], location: Optional[str]) -> WorkAuth:
    description = description or ""
    location = location or ""

    explicit: list[str] = []
    evidence: list[str] = []
    for m in _AUTH_LEADS.finditer(description):
        lugar = _place_after(description, m.end())
        if lugar:
            explicit += lugar
            evidence.append(description[m.start() : m.end() + _PLACE_WINDOW].strip())
    for m in _ONLY_AFTER.finditer(description):
        explicit += regions_in(m.group("place"))
        evidence.append(m.group(0))
    m = _CITIZEN_US.search(description)
    if m:
        explicit.append("US")
        evidence.append(m.group(0))

    no_sponsor = _NO_SPONSOR.search(description)
    if no_sponsor:
        evidence.append(no_sponsor.group(0))

    if explicit:
        regions = tuple(dict.fromkeys(explicit))
        return WorkAuth(regions, True, bool(no_sponsor), evidence)

    por_ubicacion: tuple[str, ...] = ()
    if location and not _GLOBAL_RE.search(location):
        por_ubicacion = tuple(dict.fromkeys(regions_in(location)))
    return WorkAuth(por_ubicacion, False, bool(no_sponsor), evidence)


def region_name(code: Optional[str]) -> str:
    return _NAMES.get(code or "", code or "")


async def user_country(db, user_id) -> Optional[str]:
    """El pais del perfil de un usuario, para los endpoints que sirven vacantes."""
    from sqlalchemy import select

    from app.models.career_profile import CareerProfile

    info = (
        await db.execute(select(CareerProfile.contact_info).where(CareerProfile.user_id == user_id))
    ).scalar_one_or_none()
    return profile_country(type("P", (), {"contact_info": info or {}})())


def profile_country(profile) -> Optional[str]:
    """Pais del perfil: contact_info.country, y si falta, la ciudad/ubicacion."""
    info = getattr(profile, "contact_info", None) or {}
    for clave in ("country", "location", "city"):
        code = country_code(info.get(clave))
        if code:
            return code
    return None
