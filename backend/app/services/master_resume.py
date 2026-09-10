"""The master CV: the whole career profile rendered as a CV, with no job attached.

Tailored CVs (resume_versions) come out of resume_adapter, which reorders the
profile for one posting and, with AI, rewrites it toward that posting's
wording. The master CV is the profile itself: every entry, in the profile's
own order, in the requested language.

It is rendered by exactly the same code as the tailored CVs — resume_pdf,
resume_latex and resume_text — so every fix those carry applies here without
being written twice: the email leading the contact line, tracking stripped
from links, an in-progress degree reading "2020 – Present" rather than a
graduation year, a degree that does not repeat its own field.

It also carries three things a tailored CV does not: the headline under the
name, certifications, and spoken languages. The renderers print each only when
the content has it, which is why adding them changed nothing about the
tailored CVs.

What it deliberately does not do is translate with AI. Prose comes from the
profile's own translations (see profile_i18n); the handful of terms that are
ordinary words — soft skills, language names, proficiency levels — come from
profile_i18n's glossary; everything else prints exactly as stored.
"""

from __future__ import annotations

from typing import Any

from app.services.profile_i18n import localize_profile, localize_term, normalize_language


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _skill_names(skills: Any, language: str) -> list[str]:
    """Skill display names, translated where they are words and de-duplicated.

    De-duplication matters because the glossary folds two spellings into one:
    a profile edited in both languages can hold "Liderazgo" and "Leadership",
    and printing "Leadership, Leadership" on a CV reads as padding."""
    seen: set[str] = set()
    names: list[str] = []
    for skill in skills or []:
        raw = skill.get("name") if isinstance(skill, dict) else skill
        name = localize_term(raw, language)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        names.append(name)
    return names


def master_resume_content(profile: Any, language: str | None) -> dict[str, Any]:
    """The profile as renderer-ready CV content in `language`.

    The shape matches resume_versions.content, plus `headline`,
    `certifications` and `languages`."""
    code = normalize_language(language)
    localized = localize_profile(profile, code)

    experience = [
        {
            "company": _text(entry.get("company")),
            "title": _text(entry.get("title")),
            "start_date": entry.get("start_date"),
            "end_date": entry.get("end_date"),
            "location": _text(entry.get("location")),
            "bullets": [_text(b) for b in (entry.get("bullets") or []) if _text(b)],
        }
        for entry in localized.experience
        if isinstance(entry, dict)
    ]

    education = [
        {
            "institution": _text(entry.get("institution")),
            "degree": _text(entry.get("degree")),
            "field": _text(entry.get("field")),
            "start_date": entry.get("start_date"),
            "end_date": entry.get("end_date"),
        }
        for entry in localized.education
        if isinstance(entry, dict)
    ]

    # Certification names and issuers are proper nouns: printed as stored.
    certifications = [
        {
            "name": _text(cert.get("name")),
            "issuer": _text(cert.get("issuer")),
            "date": _text(cert.get("date")),
        }
        for cert in (localized.certifications or [])
        if isinstance(cert, dict) and _text(cert.get("name"))
    ]

    languages = [
        {
            "name": localize_term(entry.get("name"), code),
            "level": localize_term(entry.get("level"), code),
        }
        for entry in (localized.languages or [])
        if isinstance(entry, dict) and _text(entry.get("name"))
    ]

    return {
        "headline": _text(localized.headline),
        "summary": (localized.summary or "").strip(),
        "skills": _skill_names(localized.skills, code),
        "experience": experience,
        "education": education,
        "certifications": certifications,
        "languages": languages,
    }
