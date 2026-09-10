"""Keeps one career profile in more than one language.

WHY THE BASE COLUMNS ARE NOT JUST "WHATEVER THE USER TYPED"
-----------------------------------------------------------
The semantic half of the match score is TF-IDF cosine similarity -- it
compares *words*. A Spanish profile scored against an English posting
shares almost no tokens, and measured on this database that alone was the
difference between an average semantic score of 1.3 and 5.8 (peak 4.9 vs
14.7) over the same 60 postings. 143 of 157 stored jobs are in English.

So `career_profiles.headline/summary/experience` stay in BASE_LANGUAGE and
are the only text the match engine ever sees. Other languages live in
`career_profiles.translations` and surface only when a CV is *rendered* --
which is the one place a human, not a cosine, reads it.

WHAT GETS TRANSLATED
--------------------
Only prose: headline, summary, each role's title/organization/bullets, and
each degree, field of study and institution. Dates and skill names never
appear here -- they are facts, and "Xamarin" is "Xamarin" in every language.

Organization names ARE translatable, but that is an option rather than an
obligation: "Comite de Estudiantes de Ingenieria" genuinely needs an English
form, while a real employer's registered name should be left identical in
both languages so a recruiter can still find the company. Leaving a field
untranslated falls back to the base text, so "same in both" costs nothing.

A missing translation falls back to the base text rather than blanking the
section: half a CV in the wrong language still beats half a CV with a hole
in it.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

#: The language the base columns are written in -- the text the match engine
#: scores. Changing this means re-translating the base and recomputing every
#: match, so it is a deliberate one-time decision, not a per-user setting.
BASE_LANGUAGE = "en"

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "es")

LANGUAGE_NAMES = {"en": "English", "es": "Español"}

#: Section headers and the handful of fixed strings a rendered CV contains.
#: Kept here rather than in resume_pdf.py so the PDF, the plain-text export
#: and anything added later cannot drift apart.
CV_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "summary": "SUMMARY",
        "skills": "SKILLS",
        "experience": "EXPERIENCE",
        "education": "EDUCATION",
        "present": "Present",
        "resume": "Resume",
        "candidate": "Candidate",
        "role": "Role",
        "degree_join": " in ",
        "certifications": "CERTIFICATIONS",
        "languages": "LANGUAGES",
    },
    "es": {
        "summary": "RESUMEN PROFESIONAL",
        "skills": "HABILIDADES",
        "experience": "EXPERIENCIA",
        "education": "FORMACIÓN ACADÉMICA",
        "present": "Actualidad",
        "resume": "Currículum",
        "candidate": "Candidato",
        "role": "Puesto",
        "degree_join": " en ",
        "certifications": "CERTIFICACIONES",
        "languages": "IDIOMAS",
    },
}


def _term_key(value: str) -> str:
    """Lookup key that ignores accents, case and spacing."""
    decomposed = unicodedata.normalize("NFKD", value)
    bare = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(bare.lower().split())


#: Display names for the few profile terms that are ordinary words rather
#: than names. Skills are facts and normally print exactly as stored:
#: "ASP.NET" is "ASP.NET" in any language, and the skills taxonomy's
#: canonical form for it (".NET") would delete the precise keyword an ATS
#: filters on. But a soft skill typed as "Liderazgo" is a Spanish word, and
#: printed verbatim it puts Spanish into an English CV. Tailored CVs never
#: showed this because the AI adapter translates while it tailors; the
#: master CV is rendered without AI, so the words are spelled out here.
#:
#: Aliases match ignoring accents, case and spacing, so "Comunicacion",
#: "comunicación" and "Communication" all land on the same entry.
_TERM_TABLE: tuple[tuple[tuple[str, ...], str, str], ...] = (
    # Soft skills
    (("communication", "comunicacion"), "Communication", "Comunicación"),
    (("leadership", "liderazgo"), "Leadership", "Liderazgo"),
    (("teamwork", "trabajo en equipo"), "Teamwork", "Trabajo en equipo"),
    (("collaboration", "colaboracion"), "Collaboration", "Colaboración"),
    (("problem solving", "resolucion de problemas"), "Problem Solving", "Resolución de problemas"),
    (("time management", "gestion del tiempo"), "Time Management", "Gestión del tiempo"),
    (("adaptability", "adaptabilidad"), "Adaptability", "Adaptabilidad"),
    # A technical skill written as ordinary words rather than a product name
    (("api integration", "integracion de apis", "integracion de api"), "API Integration", "Integración de APIs"),
    # A product name with the wrong spacing is still that product's name
    (("springboot", "spring boot"), "Spring Boot", "Spring Boot"),
    # Spoken languages
    (("spanish", "espanol"), "Spanish", "Español"),
    (("english", "ingles"), "English", "Inglés"),
    (("portuguese", "portugues"), "Portuguese", "Portugués"),
    (("french", "frances"), "French", "Francés"),
    (("german", "aleman"), "German", "Alemán"),
    (("italian", "italiano"), "Italian", "Italiano"),
    # Proficiency. Feminine forms stay feminine in Spanish rather than being
    # "corrected": both are valid, and the person's own wording wins.
    (("native", "nativo", "lengua materna"), "Native", "Nativo"),
    (("nativa",), "Native", "Nativa"),
    (("fluent", "fluido"), "Fluent", "Fluido"),
    (("fluida",), "Fluent", "Fluida"),
    (("bilingual", "bilingue"), "Bilingual", "Bilingüe"),
    (("advanced", "avanzado"), "Advanced", "Avanzado"),
    (("avanzada",), "Advanced", "Avanzada"),
    (("intermediate", "intermedio"), "Intermediate", "Intermedio"),
    (("intermedia",), "Intermediate", "Intermedia"),
    (("basic", "basico", "beginner", "principiante"), "Basic", "Básico"),
    (("basica",), "Basic", "Básica"),
)

_TERMS: dict[str, dict[str, str]] = {
    _term_key(alias): {"en": english, "es": spanish}
    for aliases, english, spanish in _TERM_TABLE
    for alias in aliases
}


def localize_term(value: Any, language: str | None) -> str:
    """Display name of a skill, spoken language or proficiency level.

    Only terms in the table change; anything else prints exactly as stored,
    minus stray whitespace. That default is the point: a technical skill must
    never be helpfully renamed on a CV."""
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    entry = _TERMS.get(_term_key(text))
    return entry[normalize_language(language)] if entry else text


def normalize_language(language: str | None) -> str:
    """Maps anything the client sends onto a language we actually support.

    Accepts "es-DO", "ES", "es_419" and friends, because that is what
    browsers and mobile WebViews send; anything unrecognized falls back to
    the base language instead of raising, since a CV in the wrong language
    is recoverable and a 500 on export is not.
    """
    if not language:
        return BASE_LANGUAGE
    code = str(language).strip().lower().replace("_", "-").split("-")[0]
    return code if code in SUPPORTED_LANGUAGES else BASE_LANGUAGE


def labels_for(language: str | None) -> dict[str, str]:
    return CV_LABELS[normalize_language(language)]


# --- Language detection -----------------------------------------------------
# Stopword frequency, not a model: the goal is only to tell Spanish from
# English on a job description, both languages have very distinctive
# high-frequency function words, and a dependency-free check that runs in
# microseconds is the right size for "which language should this CV be in?".

_ES_STOPWORDS = {
    "de", "la", "el", "en", "y", "los", "las", "del", "que", "una", "un",
    "para", "con", "por", "se", "su", "sus", "como", "al", "es", "o",
    "experiencia", "desarrollo", "trabajo", "empresa", "equipo", "conocimientos",
}
_EN_STOPWORDS = {
    "the", "and", "of", "to", "in", "for", "with", "a", "is", "you", "we",
    "our", "will", "on", "as", "are", "be", "or", "your", "this", "that",
    "experience", "team", "work", "role", "skills", "years",
}

_WORD_RE = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)


def detect_language(text: str | None) -> str:
    """Best guess at the language of a job posting. Ties go to BASE_LANGUAGE."""
    if not text:
        return BASE_LANGUAGE
    words = _WORD_RE.findall(text.lower())
    if not words:
        return BASE_LANGUAGE
    es = sum(1 for w in words if w in _ES_STOPWORDS)
    en = sum(1 for w in words if w in _EN_STOPWORDS)
    return "es" if es > en else "en"


# --- Applying a translation over the base profile ---------------------------


class LocalizedProfile:
    """A read-only view of a CareerProfile with one language's prose applied.

    Deliberately duck-typed to look like the ORM object: resume_adapter,
    cv_evaluator and the PDF renderer all take "a profile" and read
    attributes off it, and none of them should have to learn about
    languages to keep working.
    """

    __slots__ = (
        "id", "user_id", "language", "headline", "summary", "contact_info",
        "skills", "experience", "education", "certifications", "languages",
        "screening_answers",
    )

    def __init__(self, **fields: Any) -> None:
        for key in self.__slots__:
            setattr(self, key, fields.get(key))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<LocalizedProfile language={self.language!r} headline={self.headline!r}>"


def _pick(override: Any, base: Any) -> Any:
    """Override wins only when it actually has content.

    An empty string in the translations blob means "not translated yet",
    not "this person has no summary" -- a half-filled translation must not
    punch holes in the CV.
    """
    if isinstance(override, str):
        return override if override.strip() else base
    if isinstance(override, (list, tuple)):
        cleaned = [item for item in override if str(item).strip()]
        return cleaned if cleaned else base
    return base if override is None else override


def _localize_entries(
    base_entries: Iterable[Any], overrides: Any, prose_fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Overlays translated prose onto a list of experience/education entries.

    Matched by position, which is the only thing available: entries have no
    stable id. That makes reordering the base list the one operation that
    can mismatch a translation, so the frontend edits both languages on the
    same row rather than as two independent lists.
    """
    override_list = overrides if isinstance(overrides, list) else []
    out: list[dict[str, Any]] = []
    for index, entry in enumerate(base_entries or []):
        if not isinstance(entry, dict):
            continue
        merged = dict(entry)
        override = override_list[index] if index < len(override_list) else None
        if isinstance(override, dict):
            for field in prose_fields:
                if field in override:
                    merged[field] = _pick(override.get(field), entry.get(field))
        out.append(merged)
    return out


def localize_profile(profile, language: str | None) -> LocalizedProfile:
    """Returns the profile as it should read in `language`.

    Asking for the base language (or for a language with no translation on
    file) is not an error and not a branch to skip -- it returns the same
    shape, so callers have exactly one code path.
    """
    code = normalize_language(language)
    translations = getattr(profile, "translations", None) or {}
    overlay = translations.get(code) if isinstance(translations, dict) else None
    overlay = overlay if isinstance(overlay, dict) else {}

    return LocalizedProfile(
        id=getattr(profile, "id", None),
        user_id=getattr(profile, "user_id", None),
        language=code,
        headline=_pick(overlay.get("headline"), profile.headline),
        summary=_pick(overlay.get("summary"), profile.summary),
        contact_info=profile.contact_info or {},
        skills=list(profile.skills or []),
        experience=_localize_entries(
            profile.experience,
            overlay.get("experience"),
            ("title", "company", "location", "bullets"),
        ),
        education=_localize_entries(
            profile.education,
            overlay.get("education"),
            ("degree", "field", "institution"),
        ),
        certifications=list(profile.certifications or []),
        languages=list(profile.languages or []),
        screening_answers=list(getattr(profile, "screening_answers", None) or []),
    )


def translation_status(profile) -> dict[str, dict[str, Any]]:
    """Per-language completeness, for the "both languages" UI.

    `complete` answers the only question the user actually has -- "can I
    export my CV in this language yet?" -- so it counts the fields that
    would otherwise silently fall back to the base language.
    """
    translations = getattr(profile, "translations", None) or {}
    status: dict[str, dict[str, Any]] = {}

    for code in SUPPORTED_LANGUAGES:
        if code == BASE_LANGUAGE:
            status[code] = {
                "is_base": True,
                "complete": True,
                "missing": [],
                "name": LANGUAGE_NAMES[code],
            }
            continue

        overlay = translations.get(code) if isinstance(translations, dict) else None
        overlay = overlay if isinstance(overlay, dict) else {}
        missing: list[str] = []

        if profile.headline and not str(overlay.get("headline") or "").strip():
            missing.append("headline")
        if profile.summary and not str(overlay.get("summary") or "").strip():
            missing.append("summary")

        raw_exp = overlay.get("experience")
        overlay_exp = raw_exp if isinstance(raw_exp, list) else []
        for index, entry in enumerate(profile.experience or []):
            if not isinstance(entry, dict) or not entry.get("bullets"):
                continue
            override = overlay_exp[index] if index < len(overlay_exp) else None
            translated = override.get("bullets") if isinstance(override, dict) else None
            if not [b for b in (translated or []) if str(b).strip()]:
                missing.append(f"experience[{index}].bullets")

        status[code] = {
            "is_base": False,
            "complete": not missing,
            "missing": missing,
            "name": LANGUAGE_NAMES[code],
        }

    return status
