"""PDF CV upload -> a draft CareerProfile the user reviews before saving.

Nothing here writes to the database directly and nothing is ever silently
merged into the user's real profile — the whole point of the CV Maestro
design is that it's the one place data is never overwritten without the
user seeing it first (see resume_adapter.py's docstring for the same
principle applied to job-tailored resumes). This module only ever returns a
draft; `PUT /profile` is still the only way it gets persisted.

Same two-tier pattern as the rest of the app: Claude does the actual
extraction when `ANTHROPIC_API_KEY` is configured (it's much better at
segmenting real-world resume layouts than any regex could be), with a
deliberately modest offline fallback — contact info and a flat skills list
are reliable to extract heuristically, but attributing bullets to the
correct company/role without any layout information is not, so the
fallback leaves `experience`/`education` empty rather than guess wrong.
"""

from __future__ import annotations

import io
import json
import re
from typing import Any, Optional

from fastapi import HTTPException
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.anthropic_client import (
    AI_MAX_TOKENS,
    LOW_EFFORT,
    get_anthropic_client,
    log_ai_failure,
    response_text,
)
from app.services.skills_taxonomy import extract_skills_from_text
from app.core.config import settings


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(\+?\d[\d .()-]{7,}\d)")
_URL_RE = re.compile(r"https?://[^\s,;)]+", re.IGNORECASE)
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/\S+", re.IGNORECASE)
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/\S+", re.IGNORECASE)


class CVUploadError(RuntimeError):
    pass


def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="No pudimos leer ese archivo como PDF.") from exc

    text = "\n".join(pages).strip()
    if not text:
        raise HTTPException(
            status_code=422,
            detail="Este PDF no tiene texto (parece una imagen escaneada). Sube un PDF exportado desde Word o Google Docs.",
        )
    return text


def _empty_contact_info() -> dict[str, Optional[str]]:
    return {"phone": None, "city": None, "country": None, "linkedin": None, "github": None, "portfolio": None}


def _heuristic_parse(text: str) -> dict[str, Any]:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    headline = lines[0] if lines and 3 <= len(lines[0]) <= 80 else None

    contact = _empty_contact_info()
    email_match = _EMAIL_RE.search(text)
    phone_match = _PHONE_RE.search(text)
    if phone_match:
        contact["phone"] = phone_match.group(0).strip()

    linkedin_match = _LINKEDIN_RE.search(text)
    if linkedin_match:
        contact["linkedin"] = linkedin_match.group(0).rstrip(".,;)")
    github_match = _GITHUB_RE.search(text)
    if github_match:
        contact["github"] = github_match.group(0).rstrip(".,;)")

    for url in _URL_RE.findall(text):
        low = url.lower()
        if "linkedin.com" in low or "github.com" in low:
            continue
        contact["portfolio"] = url.rstrip(".,;)")
        break

    skill_names = extract_skills_from_text(text)
    skills = [{"name": s, "category": None, "level": None, "years_experience": None} for s in skill_names]

    # Names what the user can act on, not the env var they never set: the
    # name of a backend setting tells them nothing about what to do next.
    warnings = [
        "No pudimos leer tu CV completo automáticamente, así que solo extrajimos habilidades y "
        "datos de contacto. Agrega tu experiencia y educación a mano abajo: no inventamos esa parte "
        "para no arriesgar datos incorrectos."
    ]
    if not skills:
        warnings.append("No reconocimos ninguna habilidad de nuestro catálogo en el texto del PDF.")

    return {
        "profile": {
            "headline": headline,
            "summary": None,
            "contact_info": contact,
            "skills": skills,
            "experience": [],
            "education": [],
            "certifications": [],
            "languages": [],
        },
        "generated_by": "heuristic",
        "warnings": warnings,
        "email_found": email_match.group(0) if email_match else None,
    }


SYSTEM_PROMPT = """You are a resume-parsing assistant for JobFlow AI.

You will receive the raw extracted text of a candidate's resume/CV (PDF text
extraction, so layout/whitespace may be imperfect). Extract ONLY information
that is explicitly present in the text into this exact JSON schema:

{
  "headline": "string or null — the candidate's professional title/headline, if stated",
  "summary": "string or null — a professional summary, if one exists in the text (do not write a new one)",
  "contact_info": {"phone": null, "city": null, "country": null, "linkedin": null, "github": null, "portfolio": null},
  "skills": [{"name": "string", "category": "string or null", "level": "string or null", "years_experience": number or null}],
  "experience": [{"company": "string", "title": "string", "start_date": "YYYY-MM or YYYY or null",
                   "end_date": "YYYY-MM or YYYY or null (null if current)", "location": "string or null",
                   "bullets": ["string", ...], "skills_used": ["string", ...]}],
  "education": [{"institution": "string", "degree": "string or null", "field": "string or null",
                  "start_date": "string or null", "end_date": "string or null"}],
  "certifications": [{"name": "string", "issuer": "string or null", "date": "string or null"}],
  "languages": [{"name": "string", "level": "string or null"}]
}

STRICT RULES:
- NEVER invent facts, employers, dates, skills, or achievements not present in the text.
- If a field isn't present in the resume, use null (for scalars) or an empty array (for lists) — never
  fabricate a plausible-looking value.
- Preserve the candidate's own wording for bullets/summary; you may only fix obvious OCR/extraction
  artifacts (broken line wraps), not rephrase content.
- Output ONLY the JSON object, no commentary, no markdown fences.
"""


def _try_ai_parse(text: str) -> Optional[dict[str, Any]]:
    client = get_anthropic_client()
    if client is None:
        return None

    try:
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=AI_MAX_TOKENS,
            extra_body=LOW_EFFORT,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"RESUME TEXT:\n{text[:20000]}"}],
        )
        raw = response_text(response).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
        profile = json.loads(raw)
    except Exception as exc:
        log_ai_failure("cv_upload", exc)
        return None

    # Fill in any keys the model omitted so the response always matches CareerProfileUpsert's shape.
    profile.setdefault("headline", None)
    profile.setdefault("summary", None)
    profile.setdefault("contact_info", _empty_contact_info())
    for key in ("skills", "experience", "education", "certifications", "languages"):
        profile.setdefault(key, [])

    return {"profile": profile, "generated_by": "ai", "warnings": [], "email_found": None}


def parse_cv(file_bytes: bytes) -> dict[str, Any]:
    text = extract_text_from_pdf(file_bytes)
    ai_result = _try_ai_parse(text)
    if ai_result is not None:
        return ai_result
    return _heuristic_parse(text)
