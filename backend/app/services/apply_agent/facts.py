"""El perfil del usuario como hechos que el agente puede citar.

Es lo UNICO que el agente puede poner en un formulario. Si algo no esta aqui,
la respuesta es "no se" y la completa el usuario: un formulario enviado con
experiencia inventada es peor que uno sin enviar.

Acepta tanto los modelos de SQLAlchemy como diccionarios con la misma forma,
para que el banco de prueba (app/scripts/apply_bench.py) pueda usar un perfil
de ejemplo sin base de datos.
"""

from __future__ import annotations

from typing import Any, Optional

from app.services.apply_agent.classify import topic_of


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _split_name(full_name: str) -> tuple[str, str]:
    """Primer nombre y el resto. "Juan Alfonso Alvarado" -> ("Juan",
    "Alfonso Alvarado"): en un formulario en ingles "Last Name" es todo lo que
    va despues del nombre, y partirlo distinto dejaria un apellido fuera."""
    partes = full_name.split()
    if not partes:
        return "", ""
    return partes[0], " ".join(partes[1:])


def build_facts(user: Any, profile: Any) -> dict[str, Any]:
    full_name = _text(_get(user, "full_name"))
    first, last = _split_name(full_name)
    contact = _get(profile, "contact_info") or {}

    experience = [
        {
            "company": _text(e.get("company")),
            "title": _text(e.get("title")),
            "start_date": e.get("start_date"),
            "end_date": e.get("end_date"),
            "location": _text(e.get("location")),
            # Cuatro viñetas bastan para responder "describe tu experiencia
            # con X" sin mandarle al modelo el CV entero.
            "bullets": [_text(b) for b in (e.get("bullets") or [])[:4] if _text(b)],
        }
        for e in (_get(profile, "experience") or [])
        if isinstance(e, dict)
    ]
    actual = next((e for e in experience if not e.get("end_date")), experience[0] if experience else None)

    education = [
        {
            "institution": _text(e.get("institution")),
            "degree": _text(e.get("degree")),
            "field": _text(e.get("field")),
            "start_date": e.get("start_date"),
            "end_date": e.get("end_date"),
        }
        for e in (_get(profile, "education") or [])
        if isinstance(e, dict)
    ]

    skills = []
    for skill in _get(profile, "skills") or []:
        nombre = _text(skill.get("name") if isinstance(skill, dict) else skill)
        if nombre:
            skills.append(nombre)

    screening = []
    for item in _get(profile, "screening_answers") or []:
        if not isinstance(item, dict):
            continue
        pregunta, respuesta = _text(item.get("question")), str(item.get("answer") or "").strip()
        if pregunta and respuesta:
            screening.append({"question": pregunta, "answer": respuesta, "topic": topic_of(pregunta)})

    city, country = _text(contact.get("city")), _text(contact.get("country"))
    return {
        "full_name": full_name,
        "first_name": first,
        "last_name": last,
        "email": _text(_get(user, "email")),
        "phone": _text(contact.get("phone")),
        "city": city,
        "country": country,
        "location": ", ".join(p for p in (city, country) if p),
        "linkedin": _text(contact.get("linkedin")),
        "github": _text(contact.get("github")),
        "website": _text(contact.get("portfolio")) or _text(contact.get("github")),
        "headline": _text(_get(profile, "headline")),
        "summary": str(_get(profile, "summary") or "").strip(),
        "current_company": actual["company"] if actual else "",
        "current_title": actual["title"] if actual else "",
        "experience": experience,
        "education": education,
        "skills": skills,
        "languages": [
            {"name": _text(lang.get("name")), "level": _text(lang.get("level"))}
            for lang in (_get(profile, "languages") or [])
            if isinstance(lang, dict) and _text(lang.get("name"))
        ],
        "certifications": [
            _text(c.get("name")) for c in (_get(profile, "certifications") or []) if isinstance(c, dict) and _text(c.get("name"))
        ],
        "screening": screening,
    }


def screening_for(facts: dict[str, Any], topic: Optional[str]) -> Optional[str]:
    """La respuesta guardada para un tema, si el usuario la escribio."""
    if not topic:
        return None
    for item in facts.get("screening") or []:
        if item.get("topic") == topic:
            return item["answer"]
    return None


def missing_for_agent(facts: dict[str, Any]) -> list[str]:
    """Lo que le falta al perfil para que el agente pueda llenar lo basico.
    Es la "puerta" de la fase 1: sin esto cada borrador sale lleno de huecos."""
    faltan = []
    for clave, nombre in (
        ("first_name", "nombre"),
        ("email", "correo"),
        ("phone", "teléfono"),
        ("country", "país"),
        ("linkedin", "LinkedIn"),
    ):
        if not facts.get(clave):
            faltan.append(nombre)
    if not facts.get("experience") and not facts.get("education"):
        faltan.append("experiencia o educación")
    temas = {s.get("topic") for s in facts.get("screening") or []}
    for tema, nombre in (("work_auth", "autorización de trabajo"), ("sponsorship", "patrocinio de visa")):
        if tema not in temas:
            faltan.append(f"respuesta guardada sobre {nombre}")
    return faltan
