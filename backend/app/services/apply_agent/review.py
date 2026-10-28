"""El borrador guardado (un dict, Draft.to_dict() mas lo que anade el
pipeline) y lo que el usuario contesta en la revision.

Aqui se decide, cada vez que cambia algo, si un borrador:
  * puede enviarse ya (no falta ningun obligatorio),
  * podria enviarse SOLO en modo automatico (`auto_eligible`), y por que no
    (`review_reasons`, los mismos codigos que draft.REVIEW_REASONS mas los
    del pipeline).

Las respuestas del usuario llevan `source = "user"`: son suyas, y una vez que
las dio ya no frenan nada. Por eso un consentimiento que el agente nunca
contesta si puede salir: lo marco la persona en la revision, con el texto
delante.
"""

from __future__ import annotations

from typing import Any, Optional

from app.services.apply_agent.draft import FILLED, NEEDS_USER, REVIEW_REASONS, SKIPPED

SOURCE_USER = "user"

#: Motivos que anade el pipeline, ademas de los del formulario.
EXTRA_REASONS: dict[str, str] = {
    "gate": "La oferta tiene un requisito que tu perfil no cumple (ver avisos).",
    "grounding": "El CV o la carta dicen algo que no está en tu perfil: revísalo.",
    "cover_letter": "La carta de presentación la redactó la IA: léela antes de enviar.",
    "channel": "Este destino no lo envía el agente: se envía en la página de la empresa.",
    "education": REVIEW_REASONS["education"],
}
ALL_REASONS = {**REVIEW_REASONS, **EXTRA_REASONS}

_TEXT_LIMIT = {"text": 300, "textarea": 2000}


class AnswerError(ValueError):
    """Una respuesta que no vale para ese campo. El mensaje va a la interfaz."""


def _option(field: dict[str, Any], value: Any) -> Optional[dict[str, Any]]:
    for opcion in field.get("options") or []:
        if str(opcion.get("value")) == str(value):
            return opcion
    return None


def apply_answers(content: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    """Pone las respuestas del usuario en el borrador. `answers` es
    {clave_del_campo: valor}; None o "" borra la respuesta.

    Valida contra el formulario: una opcion que no existe se rechaza entera
    (nada a medias), igual que hace el agente con las del LLM."""
    campos = {f["key"]: f for f in content.get("fields") or []}
    for clave in answers:
        if clave not in campos:
            raise AnswerError("Esa pregunta no está en el formulario.")
        if campos[clave]["type"] == "file":
            raise AnswerError("Los archivos los adjunta JobPilot: tu CV y tu carta para esta vacante.")

    for clave, valor in answers.items():
        f = campos[clave]
        vacio = valor is None or valor == "" or valor == []
        if vacio:
            f["value"], f["display"], f["source"] = None, None, "none"
            f["status"] = NEEDS_USER if f["required"] else SKIPPED
            f["reason"] = "Sin responder."
            continue
        if f["type"] == "select":
            opcion = _option(f, valor)
            if opcion is None:
                raise AnswerError(f"«{f['label'][:60]}»: esa opción no existe.")
            f["value"], f["display"] = opcion["value"], opcion["label"]
        elif f["type"] == "multiselect":
            valores = valor if isinstance(valor, list) else [valor]
            opciones = [_option(f, v) for v in valores]
            if any(o is None for o in opciones):
                raise AnswerError(f"«{f['label'][:60]}»: alguna opción no existe.")
            f["value"] = [o["value"] for o in opciones]
            f["display"] = ", ".join(o["label"] for o in opciones)
        else:
            texto = str(valor).strip()[: _TEXT_LIMIT.get(f["type"], 2000)]
            f["value"], f["display"] = texto, texto
        f["source"], f["status"], f["reason"] = SOURCE_USER, FILLED, None
    return content


def pending_required(content: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in content.get("fields") or [] if f.get("required") and f.get("status") != FILLED]


def review_reasons(content: dict[str, Any], channel: str) -> list[str]:
    """Por que este borrador no puede salir solo. Misma logica que
    draft._finish, salvo que lo que respondio el usuario ya no frena."""
    motivos: list[str] = []

    def add(code: str) -> None:
        if code not in motivos:
            motivos.append(code)

    if content.get("ai_policy"):
        add("ai_policy")
    for f in content.get("fields") or []:
        del_usuario = f.get("source") == SOURCE_USER
        if del_usuario:
            continue
        kind, required, filled = f.get("kind"), f.get("required"), f.get("status") == FILLED
        if kind == "consent" and required:
            add("consent")
        if kind == "sensitive" and required:
            add("sensitive")
        if kind == "personal" and required:
            add("personal")
        if kind == "salary" and (required or filled):
            add("salary")
        if kind == "work_auth" and (required or filled):
            add("work_auth")
        if kind == "open_text" and f.get("source") == "ai":
            add("open_text")
        if required and not filled:
            add("needs_user")
    if content.get("education_required"):
        add("education")
    if any(g.get("level") == "block" for g in content.get("gates") or []):
        add("gate")
    if not (content.get("grounding") or {}).get("ok", True):
        add("grounding")
    carta = (content.get("documents") or {}).get("cover_letter") or {}
    if carta.get("generated_by") == "ai" and not carta.get("reviewed"):
        add("cover_letter")
    if channel == "external":
        add("channel")
    return motivos


def refresh(content: dict[str, Any], channel: str) -> tuple[bool, list[str]]:
    """(auto_eligible, motivos) y los deja escritos en el contenido."""
    motivos = review_reasons(content, channel)
    content["review_reasons"] = motivos
    content["review_reason_texts"] = [ALL_REASONS[m] for m in motivos if m in ALL_REASONS]
    content["pending_required"] = [f["key"] for f in pending_required(content)]
    campos = content.get("fields") or []
    obligatorios = [f for f in campos if f.get("required")]
    content["stats"] = {
        "total": len(campos),
        "required": len(obligatorios),
        "filled": sum(1 for f in campos if f.get("status") == FILLED),
        "required_filled": sum(1 for f in obligatorios if f.get("status") == FILLED),
        "needs_user": sum(1 for f in campos if f.get("status") == NEEDS_USER),
        "by_ai": sum(1 for f in campos if f.get("source") == "ai"),
        "by_user": sum(1 for f in campos if f.get("source") == SOURCE_USER),
    }
    return not motivos, motivos
