"""Lee de vuelta el PDF que acabamos de generar y comprueba que un ATS lo entiende.

Por que existe
--------------
resume_pdf.py dice "ATS-safe" en su cabecera, resume_adapter.py lo lleva en el
system prompt, y el proyecto lo repite en nueve sitios. Nada lo comprobaba
nunca. Se renderizaba el PDF y no se volvia a abrir.

Eso es exactamente la leccion L-001 del equipo -- cargar no es funcionar. Un
LaTeX o un reportlab que terminan sin error no garantizan nada sobre la capa de
texto resultante: un PDF puede compilar perfecto y extraer las palabras
pegadas, en otro orden, o directamente vacio si algo acabo dibujado en vez de
escrito. El usuario no puede verlo: abre el PDF, lo ve bien, y lo manda. El
formulario de Greenhouse o Workday al otro lado lee la capa de texto, no la
pagina, y lo que falle ahi falla en silencio -- la candidatura simplemente no
prospera y nadie sabe por que.

Asi que este modulo hace la unica verificacion que vale: ejerce el recurso de
verdad. Extrae el texto con la misma clase de parser que usa un ATS y
comprueba, sobre lo extraido, que esta lo que tiene que estar.

Que NO promete
--------------
Que te llamen. Esto mide que la maquina pueda leer el archivo, no que el
contenido convenza a nadie. Un PDF con veredicto limpio y un CV flojo siguen
siendo un CV flojo.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

from pypdf import PdfReader

from app.services.profile_i18n import labels_for

#: Por debajo de esto no hay capa de texto que valga: un CV real de una pagina
#: pasa de 1.500 caracteres con holgura. 200 deja margen para un CV minimo sin
#: dar por bueno un PDF practicamente vacio.
_MIN_EXTRACTABLE_CHARS = 200

#: Una "palabra" mas larga que esto casi siempre significa que el extractor
#: perdio los espacios y pego varias: "IngenieroBackendSeniorPythonDocker".
_IMPLAUSIBLE_WORD_LEN = 30

#: Proporcion de caracteres que deberian ser espacios en prosa normal. Muy por
#: debajo de 0,08 el texto salio pegado aunque ninguna palabra suelta llame la
#: atencion.
_MIN_SPACE_RATIO = 0.08

Level = Literal["error", "warning"]


@dataclass
class AtsFinding:
    level: Level
    code: str
    message: str


@dataclass
class AtsReport:
    #: False cuando hay algun `error`: el archivo no deberia enviarse asi.
    readable: bool
    pages: int
    extracted_chars: int
    findings: list[AtsFinding] = field(default_factory=list)
    keywords_found: list[str] = field(default_factory=list)
    keywords_missing: list[str] = field(default_factory=list)


def _fold(text: str) -> str:
    """Minusculas y sin acentos, para comparar como compara un ATS."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def extract_text(pdf_bytes: bytes) -> tuple[str, int]:
    """El texto tal y como lo ve un parser, y el numero de paginas."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages), len(reader.pages)


def _keywords_from_content(content: dict[str, Any]) -> list[str]:
    """Las habilidades del CV adaptado. Son lo que un filtro por palabras clave
    busca, y lo que resume_adapter puso ahi a proposito para esta vacante."""
    out: list[str] = []
    for skill in content.get("skills") or []:
        if isinstance(skill, str) and skill.strip():
            out.append(skill.strip())
        elif isinstance(skill, dict) and (skill.get("name") or "").strip():
            out.append(skill["name"].strip())
    return out


def check_resume_pdf(
    pdf_bytes: bytes,
    *,
    full_name: str,
    email: str | None,
    content: dict[str, Any],
    language: str = "en",
) -> AtsReport:
    """Verifica el PDF ya renderizado. Nunca lanza: un fallo al abrirlo es en si
    mismo el peor resultado posible y se reporta como tal."""
    try:
        text, pages = extract_text(pdf_bytes)
    except Exception as exc:  # noqa: BLE001 - un PDF ilegible es el hallazgo
        return AtsReport(
            readable=False,
            pages=0,
            extracted_chars=0,
            findings=[
                AtsFinding(
                    "error",
                    "unreadable",
                    f"El PDF no se puede abrir con un lector estandar ({exc.__class__.__name__}). "
                    "Un ATS lo rechazaria igual.",
                )
            ],
        )

    findings: list[AtsFinding] = []
    folded = _fold(text)
    stripped = text.strip()

    # 1. Capa de texto. Un PDF de imagenes se ve perfecto y es invisible.
    if len(stripped) < _MIN_EXTRACTABLE_CHARS:
        findings.append(
            AtsFinding(
                "error",
                "no_text_layer",
                f"Solo se extraen {len(stripped)} caracteres: el PDF no tiene capa de texto "
                "utilizable. Para un ATS esta practicamente en blanco.",
            )
        )

    # 2. El correo. Es la clave con la que cada ATS crea tu ficha de candidato;
    #    si no lo lee, no hay ficha que actualizar.
    if email:
        if _fold(email) not in folded:
            findings.append(
                AtsFinding(
                    "error",
                    "email_missing",
                    "Tu correo no aparece en el texto extraido. Es el campo con el que el ATS "
                    "identifica tu candidatura.",
                )
            )

    # 3. El nombre, apellido a apellido: algunos extractores parten la linea de
    #    contacto y comprobar la cadena entera daria un falso negativo.
    name_parts = [p for p in re.split(r"\s+", full_name.strip()) if len(p) > 1]
    missing_parts = [p for p in name_parts if _fold(p) not in folded]
    if name_parts and missing_parts:
        findings.append(
            AtsFinding(
                "error",
                "name_missing",
                "Tu nombre no se lee completo en el texto extraido "
                f"(falta: {', '.join(missing_parts)}).",
            )
        )

    # 4. Cabeceras de seccion. Es como el parser sabe donde empieza la
    #    experiencia; sin ellas suele volcarlo todo en un campo de notas.
    labels = labels_for(language)
    expected_sections = {
        "experience": bool(content.get("experience")),
        "education": bool(content.get("education")),
        "skills": bool(content.get("skills")),
    }
    missing_sections = [
        labels[key] for key, present in expected_sections.items()
        if present and _fold(labels[key]) not in folded
    ]
    if missing_sections:
        findings.append(
            AtsFinding(
                "warning",
                "sections_missing",
                "No se leen estas cabeceras: " + ", ".join(missing_sections)
                + ". El ATS puede no saber separar las secciones.",
            )
        )

    # 5. Integridad de las palabras. El fallo mas traicionero: el PDF se ve
    #    bien y el texto sale sin espacios.
    if stripped:
        space_ratio = (text.count(" ") + text.count("\n")) / len(text)
        glued = [w for w in re.findall(r"\S+", text) if len(w) > _IMPLAUSIBLE_WORD_LEN]
        if space_ratio < _MIN_SPACE_RATIO:
            findings.append(
                AtsFinding(
                    "error",
                    "text_glued",
                    "Las palabras salen pegadas al extraer el texto "
                    f"(solo {space_ratio:.1%} de separadores). El ATS leeria una sola cadena.",
                )
            )
        elif len(glued) >= 3:
            findings.append(
                AtsFinding(
                    "warning",
                    "words_glued",
                    f"{len(glued)} fragmentos salen sin separar, por ejemplo «{glued[0][:40]}».",
                )
            )

    # 6. Las habilidades que resume_adapter puso para ESTA vacante. Si una no
    #    llega al texto, se perdio en el renderizado -- y es justo la palabra
    #    por la que filtran.
    keywords = _keywords_from_content(content)
    found = [k for k in keywords if _fold(k) in folded]
    missing = [k for k in keywords if _fold(k) not in folded]
    if missing:
        findings.append(
            AtsFinding(
                "warning",
                "keywords_missing",
                f"{len(missing)} habilidades del CV no aparecen en el texto extraido: "
                + ", ".join(missing[:5])
                + ("…" if len(missing) > 5 else ""),
            )
        )

    # 7. Longitud. No es un fallo tecnico, es una advertencia de oficio.
    if pages > 3:
        findings.append(
            AtsFinding(
                "warning",
                "too_long",
                f"{pages} paginas. Por encima de dos, la mayoria de los reclutadores "
                "solo miran la primera.",
            )
        )

    return AtsReport(
        readable=not any(f.level == "error" for f in findings),
        pages=pages,
        extracted_chars=len(stripped),
        findings=findings,
        keywords_found=found,
        keywords_missing=missing,
    )
