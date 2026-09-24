"""CV Quality evaluator — flags where a user's career_profile (the "CV
Maestro") itself is weak, independent of any specific job posting.

This is deliberately separate from match_engine.py: the match engine scores
a profile *against one job*; this module scores the profile *on its own
merits* (completeness, quantified impact, skills breadth, ATS-safety) so a
user knows what to fix before they even start applying. Same design
philosophy as the rest of the app: fully offline, rule-based, explainable —
with an optional short AI-written summary on top when ANTHROPIC_API_KEY is
configured, and a deterministic fallback sentence when it isn't.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.services.anthropic_client import (
    AI_MAX_TOKENS,
    LOW_EFFORT,
    get_anthropic_client,
    log_ai_failure,
    response_text,
)
from app.services.skills_taxonomy import canonical_skill_set, normalize_skill
from app.core.config import settings


CATEGORY_WEIGHTS = {
    "completeness": 0.35,
    "impact": 0.35,
    "skills_breadth": 0.15,
    "ats_safety": 0.15,
}

WEAK_OPENERS = [
    "responsable de", "encargado de", "encargada de", "trabajé en", "trabaje en",
    "participé en", "participe en", "ayudé a", "ayude a", "colaboré en", "colabore en",
    "responsible for", "worked on", "helped with", "in charge of", "participated in",
]

_HAS_NUMBER_RE = re.compile(r"\d")
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)
_YEAR_DATE_RE = re.compile(r"^\d{4}(-\d{2})?$")


def _issue(severity: str, category: str, message: str) -> dict[str, str]:
    return {"severity": severity, "category": category, "message": message}


def _clamp(score: float) -> float:
    return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------


def _evaluate_completeness(profile: Any) -> dict[str, Any]:
    score = 100.0
    issues: list[dict[str, str]] = []

    headline = (profile.headline or "").strip()
    summary = (profile.summary or "").strip()
    skills = profile.skills or []
    experience = profile.experience or []
    education = profile.education or []
    contact = profile.contact_info or {}

    if not headline:
        score -= 20
        issues.append(_issue("error", "completeness", "Falta un titular profesional (headline)."))

    if not summary:
        score -= 15
        issues.append(_issue("error", "completeness", "Falta un resumen profesional."))
    elif len(summary) < 40:
        score -= 8
        issues.append(
            _issue(
                "warning",
                "completeness",
                "El resumen es muy corto; agrega 2-3 frases sobre tu perfil, especialidad y objetivo.",
            )
        )

    if not experience:
        score -= 25
        issues.append(_issue("error", "completeness", "No hay experiencia laboral registrada."))

    skills_count = len(skills)
    if skills_count == 0:
        score -= 20
        issues.append(_issue("error", "completeness", "No hay habilidades registradas."))
    elif skills_count <= 2:
        score -= 8
        issues.append(
            _issue(
                "warning",
                "completeness",
                f"Tienes pocas habilidades registradas ({skills_count}); agrega al menos 5-8 relevantes.",
            )
        )

    if not education:
        score -= 5
        issues.append(
            _issue("info", "completeness", "No hay estudios registrados (opcional, pero recomendable).")
        )

    if not (contact.get("linkedin") or contact.get("portfolio") or contact.get("github")):
        score -= 5
        issues.append(
            _issue(
                "info",
                "completeness",
                "Agrega un enlace a LinkedIn, GitHub o portafolio para que puedan verificar tu perfil.",
            )
        )

    return {"score": _clamp(score), "issues": issues}


# ---------------------------------------------------------------------------
# Impact / quantification
# ---------------------------------------------------------------------------


def _all_bullets(experience: list[dict[str, Any]]) -> list[str]:
    bullets: list[str] = []
    for entry in experience:
        if not isinstance(entry, dict):
            continue
        bullets.extend([b for b in (entry.get("bullets") or []) if isinstance(b, str) and b.strip()])
    return bullets


def _evaluate_impact(profile: Any) -> dict[str, Any]:
    experience = profile.experience or []
    issues: list[dict[str, str]] = []

    for entry in experience:
        if not isinstance(entry, dict):
            continue
        if not (entry.get("bullets") or []):
            title = entry.get("title") or "este rol"
            company = entry.get("company") or ""
            where = f"{title} en {company}" if company else title
            issues.append(_issue("warning", "impact", f"El rol de {where} no tiene logros (bullets) descritos."))

    bullets = _all_bullets(experience)
    if not bullets:
        issues.append(_issue("error", "impact", "Ningún rol tiene logros (bullets) descritos todavía."))
        return {"score": 0.0, "issues": issues}

    total = len(bullets)
    quantified = sum(1 for b in bullets if _HAS_NUMBER_RE.search(b))
    weak = sum(1 for b in bullets if b.strip().lower().startswith(tuple(WEAK_OPENERS)))
    short = sum(1 for b in bullets if len(b.split()) < 6)

    quantified_ratio = quantified / total
    weak_ratio = weak / total
    short_ratio = short / total

    score = 100.0 * (0.5 * quantified_ratio + 0.3 * (1 - weak_ratio) + 0.2 * (1 - short_ratio))

    if quantified_ratio < 0.3:
        issues.append(
            _issue(
                "warning",
                "impact",
                f"Solo {quantified} de {total} logros incluyen números o métricas (%, $, cantidades). "
                "Cuantificar el impacto pesa mucho más: 'reduje el tiempo de build en 40%' dice más que "
                "'mejoré el proceso de build'.",
            )
        )
    if weak_ratio > 0.3:
        issues.append(
            _issue(
                "warning",
                "impact",
                f"{weak} de {total} logros empiezan con frases pasivas ('responsable de', 'encargado de', "
                "'trabajé en'). Usa verbos de acción: diseñé, lideré, reduje, implementé, automaticé...",
            )
        )
    if short_ratio > 0.3:
        issues.append(
            _issue(
                "info",
                "impact",
                f"{short} de {total} logros son muy breves (menos de 6 palabras); agrega contexto y resultado.",
            )
        )

    return {"score": _clamp(score), "issues": issues}


# ---------------------------------------------------------------------------
# Skills breadth
# ---------------------------------------------------------------------------


def _skills_breadth_score(count: int) -> float:
    if count == 0:
        return 0.0
    if count <= 2:
        return 40.0
    if count <= 4:
        return 65.0
    if count <= 7:
        return 85.0
    return 100.0


def _evaluate_skills(profile: Any) -> dict[str, Any]:
    skills = profile.skills or []
    experience = profile.experience or []
    issues: list[dict[str, str]] = []

    score = _skills_breadth_score(len(skills))

    missing_years = [s.get("name") for s in skills if isinstance(s, dict) and s.get("name") and not s.get("years_experience")]
    if missing_years:
        # Written out rather than "habilidad(es)": this is read by one person
        # about their own CV, and the count is known here.
        count = len(missing_years)
        subject = "1 habilidad no tiene" if count == 1 else f"{count} habilidades no tienen"
        issues.append(
            _issue(
                "info",
                "skills_breadth",
                f"{subject} años de experiencia asignados. Esto ayuda al "
                "motor de match a comparar mejor contra lo que pide cada vacante.",
            )
        )

    known = canonical_skill_set([s.get("name", "") for s in skills if isinstance(s, dict)])
    used_elsewhere: set[str] = set()
    used_display: dict[str, str] = {}
    for entry in experience:
        if not isinstance(entry, dict):
            continue
        for raw in entry.get("skills_used") or []:
            canon = normalize_skill(raw)
            if canon not in known:
                used_elsewhere.add(canon)
                used_display[canon] = raw

    if used_elsewhere:
        names = ", ".join(sorted(used_display[c] for c in used_elsewhere)[:5])
        issues.append(
            _issue(
                "warning",
                "skills_breadth",
                f"Usaste estas habilidades en tu experiencia pero no están en tu lista de habilidades: "
                f"{names}. Agrégalas para que el match las detecte.",
            )
        )

    return {"score": _clamp(score), "issues": issues}


# ---------------------------------------------------------------------------
# ATS safety
# ---------------------------------------------------------------------------


def _evaluate_ats_safety(profile: Any) -> dict[str, Any]:
    score = 100.0
    issues: list[dict[str, str]] = []

    text_fields = [profile.headline or "", profile.summary or ""] + _all_bullets(profile.experience or [])
    emoji_hits = sum(1 for t in text_fields if _EMOJI_RE.search(t))
    if emoji_hits:
        score -= min(20, emoji_hits * 5)
        issues.append(
            _issue(
                "warning",
                "ats_safety",
                "Evita emojis o símbolos poco comunes en tu CV — muchos sistemas ATS los ignoran o los "
                "leen mal.",
            )
        )

    long_bullets = [b for b in _all_bullets(profile.experience or []) if len(b) > 220]
    if long_bullets:
        score -= min(15, len(long_bullets) * 4)
        issues.append(
            _issue(
                "info",
                "ats_safety",
                f"{'1 logro es muy largo' if len(long_bullets) == 1 else f'{len(long_bullets)} logros son muy largos'}"
                " (más de 220 caracteres); los reclutadores escanean el CV en segundos, sé conciso.",
            )
        )

    bad_dates = []
    for entry in profile.experience or []:
        if not isinstance(entry, dict):
            continue
        start = entry.get("start_date")
        if start and not _YEAR_DATE_RE.match(str(start).strip()):
            bad_dates.append(entry.get("company") or "un rol")
    if bad_dates:
        score -= min(15, len(bad_dates) * 5)
        issues.append(
            _issue(
                "info",
                "ats_safety",
                "Algunas fechas de inicio no tienen un formato reconocible (usa AAAA o AAAA-MM): "
                + ", ".join(bad_dates[:4]) + ".",
            )
        )

    return {"score": _clamp(score), "issues": issues}


# ---------------------------------------------------------------------------
# Strengths (positive callouts, shown alongside the issues)
# ---------------------------------------------------------------------------


def _collect_strengths(profile: Any, impact: dict[str, Any], skills_eval: dict[str, Any]) -> list[str]:
    strengths: list[str] = []
    bullets = _all_bullets(profile.experience or [])

    if bullets:
        quantified = sum(1 for b in bullets if _HAS_NUMBER_RE.search(b))
        if quantified / len(bullets) >= 0.6:
            strengths.append("Buena parte de tus logros incluyen métricas concretas — justo lo que buscan los reclutadores.")

    if len(profile.skills or []) >= 8:
        strengths.append("Tienes un buen catálogo de habilidades registradas.")

    summary = (profile.summary or "").strip()
    if 80 <= len(summary) <= 400:
        strengths.append("Tu resumen tiene una longitud adecuada.")

    if len(profile.experience or []) >= 2 and all(
        isinstance(e, dict) and (e.get("bullets") or []) for e in (profile.experience or [])
    ):
        strengths.append("Todos tus roles tienen logros descritos, no solo el título del puesto.")

    return strengths


# ---------------------------------------------------------------------------
# Optional AI summary
# ---------------------------------------------------------------------------


SYSTEM_PROMPT = """You are a candid, encouraging resume coach for JobFlow AI.

You'll be given a rule-based CV evaluation (scores + issues, already computed
— do not recompute or contradict them) for a candidate's profile. Write a
short summary in Spanish: 2-3 sentences, warm but honest, naming the ONE or
TWO highest-impact fixes first (prioritize "error" severity, then
"warning"). No markdown, no bullet points, no greeting — just the paragraph.
"""


def _try_ai_summary(evaluation: dict[str, Any]) -> Optional[str]:
    client = get_anthropic_client()
    if client is None:
        return None

    try:
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=AI_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"EVALUACIÓN:\n{json.dumps(evaluation, default=str, ensure_ascii=False)}",
                }
            ],
        )
        text = response_text(response).strip()
        return text or None
    except Exception as exc:
        log_ai_failure("cv_evaluator", exc)
        return None


def _fallback_summary(overall: float, top_issues: list[dict[str, str]]) -> str:
    if not top_issues:
        return "Tu CV está en buena forma — no encontramos señales de alerta importantes en este momento."
    lead = top_issues[0]["message"]
    if overall < 50:
        return f"Tu CV necesita trabajo antes de empezar a aplicar. Lo más urgente: {lead}"
    if overall < 75:
        return f"Vas por buen camino, pero hay espacio para mejorar. Empieza por esto: {lead}"
    return f"Tu CV está sólido. Para pulirlo aún más: {lead}"


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def evaluate_cv(profile: Any) -> dict[str, Any]:
    completeness = _evaluate_completeness(profile)
    impact = _evaluate_impact(profile)
    skills_breadth = _evaluate_skills(profile)
    ats_safety = _evaluate_ats_safety(profile)

    categories = {
        "completeness": completeness,
        "impact": impact,
        "skills_breadth": skills_breadth,
        "ats_safety": ats_safety,
    }

    overall = sum(categories[c]["score"] * w for c, w in CATEGORY_WEIGHTS.items())
    overall = round(_clamp(overall), 1)

    if overall >= 90:
        band = "Excelente"
    elif overall >= 75:
        band = "Sólido"
    elif overall >= 50:
        band = "En progreso"
    else:
        band = "Necesita trabajo"

    all_issues = [i for cat in categories.values() for i in cat["issues"]]
    all_issues.sort(key=lambda i: _SEVERITY_ORDER.get(i["severity"], 3))
    top_issues = all_issues[:6]

    strengths = _collect_strengths(profile, impact, skills_breadth)

    result = {
        "overall_score": overall,
        "band": band,
        "categories": categories,
        "top_issues": top_issues,
        "strengths": strengths,
    }

    ai_summary = _try_ai_summary(result)
    result["summary"] = ai_summary or _fallback_summary(overall, top_issues)
    result["summary_generated_by"] = "ai" if ai_summary else "manual"

    return result
