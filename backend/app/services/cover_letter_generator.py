"""Generates a personalized, professional cover letter referencing the
specific company, role, and 2-3 concrete matched qualifications.

Uses the Anthropic Messages API (model "claude-sonnet-5") when
ANTHROPIC_API_KEY is set; otherwise falls back to a clearly job-specific
template (interpolating company/title/matched skills) so the feature degrades
gracefully rather than failing.
"""

from __future__ import annotations

from typing import Any, Optional

from app.services.anthropic_client import (
    AI_MAX_TOKENS,
    LOW_EFFORT,
    get_anthropic_client,
    log_ai_failure,
    response_text,
)
from app.core.config import settings


SYSTEM_PROMPT = """You are a career-writing assistant for JobFlow AI, writing a
cover letter on behalf of a job candidate.

Write a sincere, professional, non-generic cover letter (not robotic
boilerplate) of about 3-4 short paragraphs. It must:
- Reference the specific company name and job title.
- Reference 2-3 concrete matched qualifications/skills from the candidate's
  profile that fit this job, described truthfully based on the profile given.
- Avoid fabricating experience, employers, titles, or metrics not present in
  the candidate's profile.
- Match the requested tone.
- Output ONLY the letter body text (no subject line, no markdown, no
  placeholders like [Your Name] left unresolved — sign off with the
  candidate's name if given).
"""


def _matched_skills_snippet(matched_skills: list[str]) -> list[str]:
    return matched_skills[:3] if matched_skills else []


def _template_cover_letter(
    candidate_name: str,
    job_title: str,
    company: str,
    matched_skills: list[str],
    profile_headline: Optional[str],
    tone: str,
) -> str:
    skills = _matched_skills_snippet(matched_skills)
    if len(skills) >= 3:
        skills_sentence = f"in particular my hands-on experience with {skills[0]}, {skills[1]}, and {skills[2]}"
    elif len(skills) == 2:
        skills_sentence = f"in particular my hands-on experience with {skills[0]} and {skills[1]}"
    elif len(skills) == 1:
        skills_sentence = f"in particular my hands-on experience with {skills[0]}"
    else:
        skills_sentence = "the skills and experience outlined in my profile"

    role_line = profile_headline or "a professional in this field"

    greeting = "Dear Hiring Team," if tone != "casual" else "Hi there,"
    closing = "Sincerely," if tone != "casual" else "Best,"

    paragraphs = [
        f"{greeting}",
        (
            f"I'm writing to express my interest in the {job_title} position at {company}. "
            f"As {role_line}, I was glad to see how closely this role lines up with the work I enjoy "
            f"and the skills I've built over my career."
        ),
        (
            f"What draws me most to this opportunity is the chance to apply {skills_sentence} to the "
            f"problems your team is solving at {company}. I've consistently focused on delivering "
            f"reliable, well-tested work, and I'd welcome the chance to bring that same focus to this role."
        ),
        (
            f"I'd love the opportunity to talk more about how my background could contribute to {company}'s "
            f"goals. Thank you for taking the time to consider my application."
        ),
        f"{closing}\n{candidate_name}".strip(),
    ]
    return "\n\n".join(p for p in paragraphs if p.strip())


def _try_anthropic_generate(
    candidate_name: str,
    job,
    profile,
    matched_skills: list[str],
    tone: str,
) -> Optional[str]:
    client = get_anthropic_client()
    if client is None:
        return None

    try:
        user_prompt = (
            f"Candidate name: {candidate_name}\n"
            f"Candidate headline: {profile.headline or ''}\n"
            f"Candidate summary: {profile.summary or ''}\n"
            f"Candidate matched qualifications for this job: {', '.join(matched_skills) or 'general fit'}\n\n"
            f"Job title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Job description (excerpt): {(job.description or '')[:1500]}\n\n"
            f"Requested tone: {tone}\n\n"
            "Write the cover letter now."
        )
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=AI_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = response_text(response)
        text = text.strip()
        return text or None
    except Exception as exc:
        log_ai_failure("cover_letter", exc)
        return None


def generate_cover_letter(
    profile,
    job,
    candidate_name: str,
    matched_skills: list[str],
    tone: str = "professional",
) -> dict[str, Any]:
    """Returns {"content": str, "tone": str, "generated_by": "ai"|"manual"}."""
    ai_text = _try_anthropic_generate(candidate_name, job, profile, matched_skills, tone)
    if ai_text:
        return {"content": ai_text, "tone": tone, "generated_by": "ai"}

    template_text = _template_cover_letter(
        candidate_name=candidate_name,
        job_title=job.title,
        company=job.company,
        matched_skills=matched_skills,
        profile_headline=profile.headline,
        tone=tone,
    )
    return {"content": template_text, "tone": tone, "generated_by": "manual"}
