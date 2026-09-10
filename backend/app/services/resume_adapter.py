"""Produces a tailored, ATS-safe resume_versions.content JSON from a career
profile + job. Never fabricates facts: it only reorders, re-emphasizes, and
truthfully rephrases what's already in the profile.

If ANTHROPIC_API_KEY is configured, uses the Anthropic Messages API (model
"claude-sonnet-5") with a strict system prompt to do the language adaptation.
Otherwise falls back to a deterministic rule-based adapter so the endpoint
works fully offline.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.services.anthropic_client import get_anthropic_client
from app.services.profile_i18n import LANGUAGE_NAMES, localize_profile, normalize_language
from app.services.skills_taxonomy import canonical_skill_set, normalize_skill

ANTHROPIC_MODEL = "claude-sonnet-5"

#: The description is the only field here with no natural size limit, and an
#: importer that lands on a careers *index* page instead of one posting can
#: store hundreds of thousands of characters (this database has a 490,000-char
#: "Careers at Microsoft" row). Sending that verbatim turns one click on
#: "Generar CV" into a ~122,000-token request. cover_letter_generator and
#: interview_prep already cap theirs at 1,500; 8,000 is more generous because
#: the adapter genuinely uses the detail to tailor wording, and it still
#: covers the 90th percentile of real postings here (9,219 chars) almost
#: whole while making a runaway row impossible.
MAX_JOB_DESCRIPTION_CHARS = 8000

SYSTEM_PROMPT = """You are an ATS resume-tailoring assistant for JobFlow AI.

You will be given a candidate's factual career profile (JSON) and a target job
posting (JSON). Produce a tailored resume as JSON with this exact shape:

{
  "summary": "2-4 sentence professional summary",
  "skills": ["skill", ...],
  "experience": [
    {"company": "", "title": "", "start_date": "", "end_date": null, "location": "",
     "bullets": ["...", ...]}
  ],
  "education": [{"institution": "", "degree": "", "field": "", "start_date": "", "end_date": ""}]
}

STRICT RULES:
- NEVER invent facts, employers, titles, dates, skills, or achievements that are
  not present in the source profile.
- You MAY reorder skills and experience bullets to emphasize what's relevant to
  the job.
- You MAY rephrase bullets to mirror the job posting's terminology, but only in
  ways that remain truthful to the original content (e.g. you may elevate
  "experience with X" into "hands-on experience with X", but you must NEVER
  claim "expert" or "X years of Y" unless the source profile supports it).
- Do not remove factual content; you may trim wording for concision.
- Output ONLY the JSON object, no commentary, no markdown fences.
- Write ALL prose (summary, bullets) in {language_name}. Keep company
  names, institutions, dates and technology names exactly as given --
  those are proper nouns, not text to translate.
"""


def _score_skill_relevance(skill_name: str, job_required: set[str], job_nice: set[str]) -> int:
    canonical = normalize_skill(skill_name)
    if canonical in job_required:
        return 2
    if canonical in job_nice:
        return 1
    return 0


def _job_skill_sets(job) -> tuple[set[str], set[str]]:
    required, nice = set(), set()
    for entry in job.skills_required or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name:
            continue
        canonical = normalize_skill(name)
        if (entry.get("importance") or "required").lower() == "nice_to_have":
            nice.add(canonical)
        else:
            required.add(canonical)
    return required, nice


def _rule_based_adapt(profile, job) -> dict[str, Any]:
    required, nice = _job_skill_sets(job)
    change_log: list[str] = []

    # --- Skills: reorder by relevance to the job, keep every original skill.
    profile_skills = list(profile.skills or [])
    scored = sorted(
        profile_skills,
        key=lambda s: _score_skill_relevance(s.get("name", "") if isinstance(s, dict) else str(s), required, nice),
        reverse=True,
    )
    skill_names = [s.get("name") if isinstance(s, dict) else str(s) for s in scored]
    skill_names = [s for s in skill_names if s]
    if skill_names and skill_names != [
        (s.get("name") if isinstance(s, dict) else str(s)) for s in profile_skills
    ]:
        change_log.append("Reordered skills to prioritize those the job requires.")

    # --- Summary: keep the profile's own summary verbatim (truthful), but
    # prepend the headline if present for ATS keyword density.
    summary = (profile.summary or "").strip()
    if not summary and profile.headline:
        summary = profile.headline
        change_log.append("Used profile headline as summary (no summary on file).")

    # --- Experience: reorder bullets within each role to surface job-relevant
    # ones first; never alter wording (kept verbatim => zero fabrication risk).
    experience_out = []
    for entry in profile.experience or []:
        if not isinstance(entry, dict):
            continue
        bullets = list(entry.get("bullets") or [])
        entry_skills = canonical_skill_set(entry.get("skills_used") or [])
        relevant = bool(entry_skills & (required | nice))

        def bullet_relevance(b: str) -> int:
            b_low = b.lower()
            return sum(1 for s in (required | nice) if s.lower() in b_low)

        reordered_bullets = sorted(bullets, key=bullet_relevance, reverse=True)
        if reordered_bullets != bullets and bullets:
            change_log.append(f"Reordered bullets for '{entry.get('title', 'role')}' at '{entry.get('company', '')}' to lead with job-relevant achievements.")

        experience_out.append(
            {
                "company": entry.get("company", ""),
                "title": entry.get("title", ""),
                "start_date": entry.get("start_date"),
                "end_date": entry.get("end_date"),
                "location": entry.get("location", ""),
                "bullets": reordered_bullets,
                "relevant": relevant,
            }
        )
    # Roles with relevant skills first, otherwise preserve original order (stable sort).
    experience_out.sort(key=lambda e: not e["relevant"])
    for e in experience_out:
        e.pop("relevant", None)

    education_out = [
        {
            "institution": e.get("institution", ""),
            "degree": e.get("degree", ""),
            "field": e.get("field", ""),
            "start_date": e.get("start_date"),
            "end_date": e.get("end_date"),
        }
        for e in (profile.education or [])
        if isinstance(e, dict)
    ]

    if not change_log:
        change_log.append("No reordering needed; profile already aligns with job requirements.")

    return {
        "content": {
            "summary": summary,
            "skills": skill_names,
            "experience": experience_out,
            "education": education_out,
        },
        "change_log": change_log,
    }


def _try_anthropic_adapt(profile, job, language: str) -> Optional[dict[str, Any]]:
    client = get_anthropic_client()
    if client is None:
        return None

    profile_json = {
        "headline": profile.headline,
        "summary": profile.summary,
        "skills": profile.skills,
        "experience": profile.experience,
        "education": profile.education,
    }
    job_json = {
        "title": job.title,
        "company": job.company,
        "description": (job.description or "")[:MAX_JOB_DESCRIPTION_CHARS],
        "requirements": job.requirements,
        "skills_required": job.skills_required,
    }

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT.replace("{language_name}", LANGUAGE_NAMES[language]),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"CAREER PROFILE:\n{json.dumps(profile_json, default=str)}\n\n"
                        f"TARGET JOB:\n{json.dumps(job_json, default=str)}\n\n"
                        "Produce the tailored resume JSON now."
                    ),
                }
            ],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        content = json.loads(text)
        return {
            "content": content,
            "change_log": [
                f"AI-adapted resume via Anthropic (claude-sonnet-5) in "
                f"{LANGUAGE_NAMES[language]}: reordered/reworded truthfully to match job terminology."
            ],
        }
    except Exception:
        # Any AI failure (network, parsing, quota) falls back to the deterministic adapter.
        return None


def adapt_resume(profile, job, language: str | None = None) -> dict[str, Any]:
    """Returns {"content", "change_log", "generated_by", "language"}.

    `language` picks which of the profile's languages the CV is written in
    (see services/profile_i18n.py). The base profile is localized FIRST, so
    the rule-based path -- which deliberately copies bullets verbatim to
    guarantee it never fabricates anything -- copies the already-translated
    bullets, and the AI path is handed source text already in the target
    language instead of being asked to translate and tailor in one step.
    """
    code = normalize_language(language)
    localized = localize_profile(profile, code)

    ai_result = _try_anthropic_adapt(localized, job, code)
    if ai_result is not None:
        ai_result["generated_by"] = "ai"
        ai_result["language"] = code
        return ai_result

    rule_result = _rule_based_adapt(localized, job)
    rule_result["generated_by"] = "manual"
    rule_result["language"] = code
    return rule_result
