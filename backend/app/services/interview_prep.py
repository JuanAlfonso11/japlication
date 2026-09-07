"""Builds an interview prep sheet for one job, grounded in the user's own CV.

This is the last stage the app didn't cover: it finds the job, scores it,
tailors the CV and drafts the letter, and then stops right where the hard
part starts. JobCopilot sells this as an "AI Mock Interviewer"; the useful
half of that isn't a chatbot to rehearse with, it's knowing *which* questions
this particular posting will produce and what in your history answers them.

Everything here obeys the same rule as the rest of the system (see the
README's "Notas de seguridad y veracidad"): it never invents experience.
Talking points are lifted from bullets already in the career profile, and
questions about skills the user does NOT have are framed as gaps to prepare
for honestly — never as answers to fake.

Works with no API key at all: the rule-based path below is the default and
is fully useful on its own. An LLM, when configured, only rewrites the same
grounded material more fluently.
"""

from typing import Optional

from app.core.config import settings

ANTHROPIC_MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You prepare a candidate for a job interview.

Absolute rules:
- NEVER invent experience, employers, dates, metrics or skills. Use only
  what the provided profile states.
- For a skill the candidate lacks, do not fabricate an answer. Say plainly
  that it's a gap and suggest how to address it honestly (adjacent
  experience they really have, or a willingness to learn).
- Answer in the same language as the job description; if unclear, Spanish.

Return concise, specific talking points, not generic interview advice."""

# Caps: a prep sheet is something you read on the way to the interview.
# Twenty questions is a document nobody opens.
_MAX_QUESTIONS = 8
_MAX_TALKING_POINTS = 3


def _profile_bullets(profile) -> list[tuple[str, str, str]]:
    """Flattens the profile into (company, title, bullet) triples so a
    talking point can always be traced back to where it came from."""
    out: list[tuple[str, str, str]] = []
    for entry in profile.experience or []:
        company = (entry.get("company") or "").strip()
        title = (entry.get("title") or "").strip()
        for bullet in entry.get("bullets") or []:
            if bullet and bullet.strip():
                out.append((company, title, bullet.strip()))
    return out


def _bullets_mentioning(skill: str, bullets: list[tuple[str, str, str]]) -> list[str]:
    needle = skill.lower().strip()
    if not needle:
        return []
    hits = [
        f"{bullet}  ({title} @ {company})" if company else bullet
        for company, title, bullet in bullets
        if needle in bullet.lower()
    ]
    return hits[:_MAX_TALKING_POINTS]


def _rule_based_questions(profile, job, matched_skills: list[str], missing_skills: list[str]) -> list[dict]:
    bullets = _profile_bullets(profile)
    questions: list[dict] = []

    # 1. Skills the candidate genuinely has and the job asked for. These are
    #    the questions most likely to be asked AND the ones with real
    #    material behind them, so they lead.
    for skill in matched_skills[:3]:
        evidence = _bullets_mentioning(skill, bullets)
        questions.append(
            {
                "question": f"Cuéntame sobre tu experiencia con {skill}.",
                "category": "tecnica",
                "why": f"{skill} aparece entre los requisitos de esta vacante y en tu perfil.",
                "talking_points": evidence
                or [
                    f"{skill} está en tus habilidades pero no aparece en ninguna viñeta de "
                    "experiencia. Prepara un ejemplo concreto de dónde lo usaste."
                ],
            }
        )

    # 2. Gaps. Named honestly, with no invented answer — the point is to not
    #    be caught flat-footed, not to bluff.
    for skill in missing_skills[:2]:
        questions.append(
            {
                "question": f"¿Qué experiencia tienes con {skill}?",
                "category": "brecha",
                "why": f"La vacante pide {skill} y no está en tu perfil. Es la pregunta que más te puede costar.",
                "talking_points": [
                    "No inventes experiencia: es lo más fácil de detectar en una entrevista técnica.",
                    "Nombra lo más cercano que sí manejas y explica en qué se parece.",
                    "Di concretamente cómo lo aprenderías y en cuánto tiempo.",
                ],
            }
        )

    # 3. Straight from the posting's own requirements, which is where an
    #    interviewer's list usually comes from.
    for requirement in (job.requirements or [])[:2]:
        text = str(requirement).strip()
        if not text:
            continue
        questions.append(
            {
                "question": f"Este puesto pide: «{text}». ¿Cómo lo cumples?",
                "category": "requisito",
                "why": "Está listado explícitamente como requisito.",
                "talking_points": [
                    "Responde con un caso puntual, no con una afirmación general.",
                ],
            }
        )

    # 4. The question every interview asks and nobody prepares.
    questions.append(
        {
            "question": f"¿Por qué {job.company}?",
            "category": "empresa",
            "why": "Se pregunta casi siempre y es donde más se nota la falta de preparación.",
            "talking_points": [
                f"Lee la descripción de la vacante de {job.company} y cita algo específico de ahí.",
                "Conecta con algo real de tu trayectoria, no con un elogio genérico a la empresa.",
            ],
        }
    )

    return questions[:_MAX_QUESTIONS]


def _try_anthropic_prep(profile, job, matched_skills, missing_skills, base: list[dict]) -> Optional[list[dict]]:
    if not settings.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    try:
        import json

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        experience_text = "\n".join(
            f"- {bullet} ({title} @ {company})" for company, title, bullet in _profile_bullets(profile)
        )[:3000]

        user_prompt = (
            f"Job title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Job description (excerpt): {(job.description or '')[:1500]}\n"
            f"Requirements: {'; '.join(str(r) for r in (job.requirements or [])[:8])}\n\n"
            f"Candidate headline: {profile.headline or ''}\n"
            f"Candidate summary: {profile.summary or ''}\n"
            f"Skills the candidate HAS that this job wants: {', '.join(matched_skills) or 'none identified'}\n"
            f"Skills the job wants that the candidate LACKS: {', '.join(missing_skills) or 'none identified'}\n"
            f"Candidate experience bullets (the ONLY facts you may use):\n{experience_text}\n\n"
            "Produce up to 8 likely interview questions for this specific posting. "
            'Reply with JSON only: {"questions": [{"question": str, "category": '
            '"tecnica"|"brecha"|"requisito"|"empresa", "why": str, "talking_points": [str]}]}'
        )
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ).strip()

        # Models sometimes wrap JSON in a fenced block despite instructions.
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]

        parsed = json.loads(text)
        questions = parsed.get("questions")
        if not isinstance(questions, list) or not questions:
            return None

        cleaned: list[dict] = []
        for item in questions[:_MAX_QUESTIONS]:
            if not isinstance(item, dict) or not item.get("question"):
                continue
            points = item.get("talking_points")
            cleaned.append(
                {
                    "question": str(item["question"]),
                    "category": str(item.get("category") or "tecnica"),
                    "why": str(item.get("why") or ""),
                    "talking_points": [str(p) for p in points][:_MAX_TALKING_POINTS]
                    if isinstance(points, list)
                    else [],
                }
            )
        return cleaned or None
    except Exception:
        # Any failure (network, quota, malformed JSON) falls back to the
        # rule-based sheet, which is already useful — never an error page.
        return None


def build_interview_prep(profile, job, matched_skills: list[str], missing_skills: list[str]) -> dict:
    """Returns {"questions": [...], "generated_by": "ai"|"manual"}."""
    base = _rule_based_questions(profile, job, matched_skills, missing_skills)

    ai_questions = _try_anthropic_prep(profile, job, matched_skills, missing_skills, base)
    if ai_questions:
        return {"questions": ai_questions, "generated_by": "ai"}

    return {"questions": base, "generated_by": "manual"}
