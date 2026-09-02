"""Hybrid weighted match engine between a user's career_profile and a job.

overall_score = 0.5 * technical_score + 0.3 * experience_score + 0.2 * semantic_score
(each sub-score is 0-100; overall rounded to 2 decimals)
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, datetime
from typing import Any, Optional

from app.services.skills_taxonomy import canonical_skill_set, normalize_skill

TECHNICAL_WEIGHT = 0.5
EXPERIENCE_WEIGHT = 0.3
SEMANTIC_WEIGHT = 0.2

YEARS_RE = re.compile(
    r"(\d+)\s*\+?\s*(?:-|to|a)?\s*(\d+)?\s*\+?\s*(?:years?|yrs?|años|anos)",
    re.IGNORECASE,
)

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "on", "at",
    "is", "are", "be", "as", "by", "we", "you", "our", "your", "this", "that",
    "will", "have", "has", "from", "it", "its", "de", "la", "el", "en", "y",
    "con", "un", "una", "los", "las", "para", "que",
}


# ---------------------------------------------------------------------------
# Technical score
# ---------------------------------------------------------------------------


def _job_skill_map(skills_required: list[dict[str, Any]]) -> dict[str, str]:
    """canonical skill name -> importance ('required' | 'nice_to_have')"""
    out: dict[str, str] = {}
    for entry in skills_required or []:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not name:
            continue
        canonical = normalize_skill(name)
        importance = (entry.get("importance") or "required").lower() if isinstance(entry, dict) else "required"
        if importance not in ("required", "nice_to_have"):
            importance = "required"
        # required takes precedence if a skill appears twice
        if canonical not in out or importance == "required":
            out[canonical] = importance
    return out


def _profile_skill_set(profile_skills: list[dict[str, Any]]) -> set[str]:
    names = []
    for s in profile_skills or []:
        if isinstance(s, dict):
            name = s.get("name")
        else:
            name = s
        if name:
            names.append(name)
    return canonical_skill_set(names)


def compute_technical_score(
    profile_skills: list[dict[str, Any]], job_skills_required: list[dict[str, Any]]
) -> tuple[float, list[str], list[str]]:
    """Returns (technical_score 0-100, matched_skills, missing_skills)."""
    job_skill_map = _job_skill_map(job_skills_required)
    if not job_skill_map:
        return 100.0, [], []

    profile_set = _profile_skill_set(profile_skills)

    weights = {"required": 2.0, "nice_to_have": 1.0}
    total_weight = sum(weights[imp] for imp in job_skill_map.values())
    matched_weight = 0.0
    matched: list[str] = []
    missing: list[str] = []

    for skill, importance in job_skill_map.items():
        if skill in profile_set:
            matched_weight += weights[importance]
            matched.append(skill)
        else:
            if importance == "required":
                missing.append(skill)

    score = (matched_weight / total_weight * 100.0) if total_weight else 100.0
    return round(min(score, 100.0), 2), matched, missing


# ---------------------------------------------------------------------------
# Experience score
# ---------------------------------------------------------------------------


def extract_required_years(*texts: str) -> Optional[float]:
    """Scan the given texts for a "N+ years" / "N-M years" / "N años" style
    requirement and return the minimum required years found (float), or None
    if no explicit requirement is present."""
    best: Optional[float] = None
    for text in texts:
        if not text:
            continue
        for match in YEARS_RE.finditer(text):
            low = float(match.group(1))
            if best is None or low < best:
                best = low
    return best


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            parsed = datetime.strptime(s, fmt)
            return parsed.date()
        except ValueError:
            continue
    return None


def _duration_years(start: Optional[date], end: Optional[date]) -> float:
    if not start:
        return 0.0
    end = end or date.today()
    days = (end - start).days
    return max(days, 0) / 365.25


def compute_relevant_experience_years(
    experience: list[dict[str, Any]], job_required_skills: set[str]
) -> float:
    """Sum durations of experience entries whose skills_used intersect the
    job's required skills. If job_required_skills is empty, sums ALL
    experience durations (total years of experience)."""
    total = 0.0
    for entry in experience or []:
        if not isinstance(entry, dict):
            continue
        skills_used = canonical_skill_set(entry.get("skills_used") or [])
        if job_required_skills and not (skills_used & job_required_skills):
            continue
        start = _parse_date(entry.get("start_date"))
        end = _parse_date(entry.get("end_date"))
        total += _duration_years(start, end)
    return round(total, 2)


def compute_experience_score(
    experience: list[dict[str, Any]],
    job_requirements: list[str],
    job_description: str,
    job_required_skills: set[str],
) -> tuple[float, Optional[float], float]:
    """Returns (experience_score 0-100, required_years|None, relevant_years)."""
    texts = list(job_requirements or []) + [job_description or ""]
    required_years = extract_required_years(*texts)
    relevant_years = compute_relevant_experience_years(experience, job_required_skills)

    if required_years is None or required_years <= 0:
        # No explicit requirement found: score gracefully based on whether the
        # candidate has *any* relevant experience, capped at 100.
        if relevant_years <= 0:
            return 60.0, required_years, relevant_years  # neutral-ish default
        return round(min(60.0 + relevant_years * 8.0, 100.0), 2), required_years, relevant_years

    ratio = relevant_years / required_years
    score = round(min(ratio, 1.0) * 100.0, 2)
    return score, required_years, relevant_years


# ---------------------------------------------------------------------------
# Semantic score (offline TF-IDF / cosine fallback; no external API required)
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    words = re.findall(r"[a-záéíóúñü0-9+#.]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = Counter(tokens)
    total = sum(tf.values()) or 1
    return {term: (count / total) * idf.get(term, 0.0) for term, count in tf.items()}


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    common = set(vec_a) & set(vec_b)
    dot = sum(vec_a[t] * vec_b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def compute_semantic_score(profile_text: str, job_text: str) -> float:
    """Offline TF-IDF cosine-similarity fallback (no external API key needed).
    Two "documents" (profile, job) -> IDF degenerates to a simple
    presence-weighted scheme, which is equivalent to a smoothed
    term-frequency cosine similarity — good enough as a lightweight semantic
    proxy without any ML dependency."""
    tokens_a = _tokenize(profile_text)
    tokens_b = _tokenize(job_text)
    if not tokens_a or not tokens_b:
        return 0.0

    vocab = set(tokens_a) | set(tokens_b)
    doc_freq = {term: (term in tokens_a) + (term in tokens_b) for term in vocab}
    idf = {term: math.log(1 + (2 / df)) for term, df in doc_freq.items()}

    vec_a = _tfidf_vector(tokens_a, idf)
    vec_b = _tfidf_vector(tokens_b, idf)
    similarity = _cosine_similarity(vec_a, vec_b)
    return round(max(0.0, min(similarity, 1.0)) * 100.0, 2)


def build_profile_text(profile) -> str:
    parts = [profile.headline or "", profile.summary or ""]
    for exp in profile.experience or []:
        if isinstance(exp, dict):
            parts.append(exp.get("title") or "")
            parts.extend(exp.get("bullets") or [])
    return " \n".join(p for p in parts if p)


def build_job_text(job) -> str:
    parts = [job.title or "", job.description or ""]
    return " \n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Concerns (rule-based, human-readable)
# ---------------------------------------------------------------------------


def build_concerns(
    required_years: Optional[float],
    relevant_years: float,
    missing_skills: list[str],
    job_seniority: Optional[str],
    profile_experience: list[dict[str, Any]],
) -> list[str]:
    concerns: list[str] = []

    if required_years is not None and relevant_years < required_years:
        concerns.append(
            f"Requiere {required_years:g}+ años de experiencia relevante; el perfil registra {relevant_years:g}."
        )

    if missing_skills:
        if len(missing_skills) == 1:
            concerns.append(f"Falta la habilidad requerida: {missing_skills[0]}.")
        else:
            preview = ", ".join(missing_skills[:5])
            more = f" y {len(missing_skills) - 5} más" if len(missing_skills) > 5 else ""
            concerns.append(f"Faltan {len(missing_skills)} habilidades requeridas: {preview}{more}.")

    if job_seniority:
        seniority_low = job_seniority.lower()
        total_years = sum(
            _duration_years(_parse_date(e.get("start_date")), _parse_date(e.get("end_date")))
            for e in (profile_experience or [])
            if isinstance(e, dict)
        )
        if any(k in seniority_low for k in ("senior", "staff", "principal", "lead", "director")) and total_years < 4:
            concerns.append(
                f"El puesto es de nivel '{job_seniority}'; el perfil tiene ~{total_years:.1f} años de experiencia total."
            )
        if any(k in seniority_low for k in ("junior", "entry", "intern")) and total_years > 8:
            concerns.append(
                f"El puesto es de nivel '{job_seniority}', posiblemente por debajo del nivel de experiencia del perfil (~{total_years:.1f} años)."
            )

    return concerns


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def compute_match(profile, job) -> dict[str, Any]:
    """profile: CareerProfile ORM instance, job: Job ORM instance.
    Returns a dict ready to persist into job_matches / return as MatchResult.
    """
    job_skill_map = _job_skill_map(job.skills_required or [])
    job_required_skill_set = {s for s, imp in job_skill_map.items() if imp == "required"} or set(job_skill_map)

    technical_score, matched_skills, missing_skills = compute_technical_score(
        profile.skills or [], job.skills_required or []
    )

    experience_score, required_years, relevant_years = compute_experience_score(
        profile.experience or [],
        [str(r) for r in (job.requirements or [])],
        job.description or "",
        job_required_skill_set,
    )

    profile_text = build_profile_text(profile)
    job_text = build_job_text(job)
    semantic_score = compute_semantic_score(profile_text, job_text)

    overall = (
        TECHNICAL_WEIGHT * technical_score
        + EXPERIENCE_WEIGHT * experience_score
        + SEMANTIC_WEIGHT * semantic_score
    )

    concerns = build_concerns(
        required_years, relevant_years, missing_skills, job.seniority, profile.experience or []
    )

    return {
        "overall_score": round(overall, 2),
        "technical_score": technical_score,
        "experience_score": experience_score,
        "semantic_score": semantic_score,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "concerns": concerns,
    }
