"""Improves the WRITING QUALITY of the user's base career profile — the
"CV principal" that every per-job tailored resume (resume_adapter.py)
starts from. This is a deliberately separate, narrower concern: it only
touches headline/summary/experience-bullet wording (clarity, grammar,
stronger verbs, concision), never facts, and never anything job-specific.
Tailoring for an individual posting stays resume_adapter.py's job — this
module never sees a Job at all.

Same two-tier pattern as the rest of the app (resume_adapter.py,
cv_upload.py): Claude does the actual rewriting when ANTHROPIC_API_KEY is
configured, with a deterministic rule-based fallback so the endpoint works
fully offline. Like CV upload, this never writes to the database itself —
it returns a *proposed* full profile for the user to review before hitting
Save (PUT /profile), so a bad rewrite never silently overwrites real data.
"""

from __future__ import annotations

import json
from typing import Any

from app.services.anthropic_client import get_anthropic_client

ANTHROPIC_MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are a CV/resume writing coach for JobPilot.

You will be given a candidate's factual career profile as JSON. Improve its
WRITING QUALITY — clarity, impact, grammar, concision, and ATS-friendliness
— without changing any facts. Return JSON with this exact shape:

{
  "headline": "improved headline",
  "summary": "improved 2-4 sentence professional summary",
  "experience": [
    {"bullets": ["improved bullet", ...]}
  ]
}

"experience" MUST have exactly one entry per input experience entry, in the
same order, with exactly the same number of bullets per entry as the input
— you are rewriting each bullet's wording, never adding, removing, or
reordering them.

STRICT RULES:
- NEVER invent employers, titles, dates, skills, metrics, or achievements
  not present in the source profile.
- You MAY rephrase for clarity and impact, fix grammar, strengthen weak
  verbs, and tighten wording — but must stay truthful to the original
  meaning. Never claim a stronger outcome than the original bullet stated.
- Do not fabricate numbers/metrics that aren't already in the bullet.
- Output ONLY the JSON object, no commentary, no markdown fences.
"""


def _profile_field(profile: Any, name: str, default: Any = None) -> Any:
    """Works whether `profile` is the CareerProfile ORM model or a plain
    dict (the router always passes the ORM model, but keeping this small
    indirection makes the module trivially unit-testable with plain dicts)."""
    if isinstance(profile, dict):
        return profile.get(name, default)
    return getattr(profile, name, default)


def _passthrough_fields(profile: Any) -> dict[str, Any]:
    return {
        "contact_info": _profile_field(profile, "contact_info") or {},
        "skills": list(_profile_field(profile, "skills") or []),
        "education": list(_profile_field(profile, "education") or []),
        "certifications": list(_profile_field(profile, "certifications") or []),
        "languages": list(_profile_field(profile, "languages") or []),
    }


def _rule_based_improve(profile: Any) -> dict[str, Any]:
    change_log: list[str] = []

    headline = (_profile_field(profile, "headline") or "").strip()
    summary = (_profile_field(profile, "summary") or "").strip()
    experience = list(_profile_field(profile, "experience") or [])
    skills = list(_profile_field(profile, "skills") or [])

    if not summary:
        skill_names = [
            s.get("name") for s in skills[:3] if isinstance(s, dict) and s.get("name")
        ]
        recent_title = None
        recent_company = None
        if experience and isinstance(experience[0], dict):
            recent_title = experience[0].get("title")
            recent_company = experience[0].get("company")
        parts = []
        if headline:
            parts.append(headline + ".")
        if recent_title and recent_company:
            parts.append(f"Currently {recent_title} at {recent_company}.")
        if skill_names:
            parts.append(f"Skilled in {', '.join(skill_names)}.")
        if parts:
            summary = " ".join(parts)
            change_log.append("Wrote a summary from your headline, most recent role, and top skills (none was on file).")

    experience_out = []
    for entry in experience:
        if not isinstance(entry, dict):
            continue
        bullets = [b.strip() for b in (entry.get("bullets") or []) if b and b.strip()]
        cleaned = [b[0].upper() + b[1:] if b and b[0].islower() else b for b in bullets]
        if cleaned != (entry.get("bullets") or []):
            change_log.append(f"Cleaned up bullet formatting for '{entry.get('title', 'role')}'.")
        experience_out.append({**entry, "bullets": cleaned})

    if not change_log:
        change_log.append("Profile writing already looked clean — no changes made.")

    return {
        "headline": headline,
        "summary": summary,
        "experience": experience_out,
        "change_log": change_log,
    }


def _try_anthropic_improve(profile: Any) -> dict[str, Any] | None:
    client = get_anthropic_client()
    if client is None:
        return None

    experience = list(_profile_field(profile, "experience") or [])
    profile_json = {
        "headline": _profile_field(profile, "headline"),
        "summary": _profile_field(profile, "summary"),
        "experience": experience,
    }

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"CAREER PROFILE:\n{json.dumps(profile_json, default=str)}\n\n"
                        "Produce the improved headline/summary/experience JSON now."
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
        parsed = json.loads(text)

        improved_experience = parsed.get("experience") or []
        if len(improved_experience) != len(experience):
            return None  # AI dropped/added an entry — don't trust it, fall back.

        experience_out = []
        for original, improved in zip(experience, improved_experience):
            if not isinstance(original, dict):
                continue
            new_bullets = improved.get("bullets") if isinstance(improved, dict) else None
            if not isinstance(new_bullets, list) or len(new_bullets) != len(original.get("bullets") or []):
                new_bullets = original.get("bullets") or []  # count mismatch — keep original bullets for this role
            experience_out.append({**original, "bullets": new_bullets})

        return {
            "headline": parsed.get("headline") or _profile_field(profile, "headline") or "",
            "summary": parsed.get("summary") or _profile_field(profile, "summary") or "",
            "experience": experience_out,
            "change_log": [
                "AI-improved via Anthropic (claude-sonnet-5): tightened headline/summary and strengthened "
                "experience bullets — same facts, clearer writing."
            ],
        }
    except Exception:
        # Any AI failure (network, parsing, quota) falls back to the deterministic improver.
        return None


def improve_profile(profile: Any) -> dict[str, Any]:
    """Returns a full proposed profile dict (every CareerProfileUpsert
    field) plus change_log/generated_by — never persisted here. Only
    headline/summary/experience bullets are reworded; contact_info,
    skills, education, certifications, and languages pass through
    unchanged since there's no "writing quality" to improve on structured
    data like that."""
    ai_result = _try_anthropic_improve(profile)
    result = ai_result if ai_result is not None else _rule_based_improve(profile)
    generated_by = "ai" if ai_result is not None else "manual"

    return {
        "profile": {
            "headline": result["headline"],
            "summary": result["summary"],
            "experience": result["experience"],
            **_passthrough_fields(profile),
        },
        "change_log": result["change_log"],
        "generated_by": generated_by,
    }
