"""Auditoria de hechos del CV y la carta antes de que salgan con tu nombre.

Es el "Factual Grounding Audit" del flujo /apply de ai-job-search (paso 3:
el revisor compara cada fecha, empleador, cargo y cifra de los borradores
con las fuentes del perfil). Alli lo hace un segundo agente; aqui lo hace
codigo, sin IA, porque corre en cada swipe y tiene que ser barato y
predecible. La regla es la misma: reformular esta bien, cambiar un hecho o
inflar un numero no.

Que se comprueba contra el perfil (todas sus columnas de texto, traducciones
incluidas, porque el CV puede ir en el otro idioma):

  * Cada empleador y cada institucion del CV existe en el perfil.
  * El cargo y las fechas de cada puesto son los del perfil.
  * Cada cifra del CV y de la carta (un "40%", "3+ years", "10,000 users")
    aparece en el perfil. Un numero que solo esta en la oferta no cuenta: la
    oferta dice lo que piden, no lo que el candidato tiene.
  * Cada habilidad del CV esta en el perfil. Esta es la unica que se ARREGLA
    sola (se quita la habilidad de mas), porque quitarla nunca puede mentir.

Lo demas no se toca: se reporta y frena el envio automatico. El usuario ve
la lista en la revision y decide.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.skills_taxonomy import canonical_skill_set


@dataclass
class GroundingReport:
    issues: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "issues": self.issues, "fixed": self.fixed}


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _fold(text: Any) -> str:
    sin_tildes = unicodedata.normalize("NFKD", str(text or ""))
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9+#.&/ ]", " ", sin_tildes).split())


def _profile_blob(profile: Any) -> str:
    partes = []
    for columna in ("headline", "summary", "skills", "experience", "education",
                    "certifications", "languages", "translations", "contact_info"):
        valor = _get(profile, columna)
        if valor:
            partes.append(valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, default=str))
    return "\n".join(partes)


#: Una cifra suelta: no pegada a letras (asi "Web3", "B2B", "S3", "ES6" no
#: cuentan) y con sus separadores de miles/decimales.
_NUMBER = re.compile(r"(?<![A-Za-z0-9])\d+(?:[.,]\d+)*(?![A-Za-z0-9])")


def _numbers(text: str) -> set[str]:
    salida = set()
    for m in _NUMBER.finditer(text or ""):
        crudo = re.sub(r"[.,]", "", m.group(0))
        valor = crudo.lstrip("0") or "0"
        # 0 y 1 aparecen en todo ("1 team", "0 to 1") y no afirman nada.
        if valor in ("0", "1"):
            continue
        salida.add(valor)
    return salida


def _date_key(value: Any) -> str:
    """'2022-03', '2022-03-01', 'Mar 2022' -> '2022-03' cuando se puede; si no,
    el texto doblado. Basta para ver si un puesto cambio de fechas."""
    texto = str(value or "").strip()
    if not texto:
        return ""
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?", texto)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}" if m.group(2) else m.group(1)
    return _fold(texto)


def _same_date(a: Any, b: Any) -> bool:
    ka, kb = _date_key(a), _date_key(b)
    if not ka or not kb:
        return True  # una fecha que falta en un lado no es una fecha cambiada
    return ka == kb or ka.startswith(kb) or kb.startswith(ka)


def _profile_entries(profile: Any, columna: str) -> list[dict[str, Any]]:
    entradas = [e for e in (_get(profile, columna) or []) if isinstance(e, dict)]
    # Los titulos traducidos tambien son del perfil: un CV en espanol dice
    # "Desarrollador" donde el perfil base dice "Developer".
    traducciones = _get(profile, "translations") or {}
    for lang in traducciones.values() if isinstance(traducciones, dict) else []:
        for i, t in enumerate((lang or {}).get(columna) or []):
            if isinstance(t, dict) and i < len(entradas):
                extra = dict(entradas[i])
                extra.update({k: v for k, v in t.items() if v})
                entradas.append(extra)
    return entradas


def audit_resume(content: dict[str, Any], profile: Any) -> tuple[dict[str, Any], GroundingReport]:
    """Devuelve (contenido corregido, informe). Solo corrige habilidades."""
    report = GroundingReport()
    content = dict(content or {})
    blob = _profile_blob(profile)
    numeros_perfil = _numbers(blob)

    # Habilidades: las de mas se quitan.
    perfil_skills = canonical_skill_set(
        [s.get("name") if isinstance(s, dict) else s for s in (_get(profile, "skills") or [])]
    )
    blob_doblado = _fold(blob)
    skills = []
    for skill in content.get("skills") or []:
        nombre = skill.get("name") if isinstance(skill, dict) else skill
        if not nombre:
            continue
        en_perfil = bool(canonical_skill_set([nombre]) & perfil_skills) or _fold(nombre) in blob_doblado
        if en_perfil:
            skills.append(skill)
        else:
            report.fixed.append(f"Se quitó «{nombre}» de tus habilidades: no está en tu perfil.")
    content["skills"] = skills

    # Puestos: empleador, cargo y fechas.
    puestos = _profile_entries(profile, "experience")
    por_empresa: dict[str, list[dict[str, Any]]] = {}
    for p in puestos:
        por_empresa.setdefault(_fold(p.get("company")), []).append(p)
    for e in content.get("experience") or []:
        if not isinstance(e, dict):
            continue
        empresa = _fold(e.get("company"))
        if not empresa:
            continue
        candidatos = por_empresa.get(empresa)
        if not candidatos:
            report.issues.append(f"El CV nombra un empleador que no está en tu perfil: «{e.get('company')}».")
            continue
        cargo = _fold(e.get("title"))
        if cargo and not any(_fold(c.get("title")) == cargo for c in candidatos):
            report.issues.append(
                f"El cargo en {e.get('company')} cambió: «{e.get('title')}» "
                f"(tu perfil dice «{candidatos[0].get('title')}»)."
            )
        if not any(_same_date(e.get("start_date"), c.get("start_date"))
                   and _same_date(e.get("end_date"), c.get("end_date")) for c in candidatos):
            report.issues.append(f"Las fechas de {e.get('company')} no coinciden con tu perfil.")

    instituciones = {_fold(x.get("institution")) for x in _profile_entries(profile, "education")}
    for ed in content.get("education") or []:
        nombre = _fold(ed.get("institution")) if isinstance(ed, dict) else ""
        if nombre and nombre not in instituciones:
            report.issues.append(f"El CV nombra una institución que no está en tu perfil: «{ed.get('institution')}».")

    # Cifras: resumen y vinetas.
    texto = " ".join(
        [str(content.get("summary") or "")]
        + [str(b) for e in content.get("experience") or [] if isinstance(e, dict) for b in e.get("bullets") or []]
    )
    for n in sorted(_numbers(texto) - numeros_perfil, key=lambda x: (len(x), x)):
        report.issues.append(f"El CV dice «{n}» y esa cifra no aparece en tu perfil.")
    return content, report


#: Una cifra que afirma algo del candidato: "5 years", "5+ años", "40%".
_CLAIM_AFTER = re.compile(r"^\s*(\+|%|years?\b|yrs?\b|a[nñ]os\b|months?\b|meses\b)", re.IGNORECASE)


def audit_cover_letter(
    text: Optional[str],
    profile: Any,
    report: Optional[GroundingReport] = None,
    job_text: Optional[str] = None,
) -> GroundingReport:
    """Las cifras de la carta. Una cifra que viene de la oferta ("vuestro
    equipo de 50 personas") se admite: habla de la empresa, no del
    candidato. Salvo que vaya como experiencia ("5 years", "40%"): eso si es
    una afirmacion sobre el, y la oferta no la respalda."""
    report = report or GroundingReport()
    text = text or ""
    numeros_perfil = _numbers(_profile_blob(profile))
    numeros_oferta = _numbers(job_text or "")
    vistos: set[str] = set()
    for m in _NUMBER.finditer(text):
        valor = re.sub(r"[.,]", "", m.group(0)).lstrip("0") or "0"
        if valor in ("0", "1") or valor in numeros_perfil or valor in vistos:
            continue
        afirma = bool(_CLAIM_AFTER.match(text[m.end():]))
        if valor in numeros_oferta and not afirma:
            continue
        vistos.add(valor)
        report.issues.append(f"La carta dice «{m.group(0)}» y esa cifra no aparece en tu perfil.")
    return report
