"""Tests for the master CV: the whole profile, downloadable like a tailored CV.

Most of what these guard is sameness. The master CV exists so the profile
gets every fix the tailored CVs carry, and the cheap way for that to rot is
for the exports to quietly diverge — a section added to one renderer but not
the others, or a tailored CV that suddenly grows a LANGUAGES heading because
the master CV needed one.

The glossary tests guard the one thing only the master CV does: it has no AI
to translate soft skills, so a Spanish word in an English CV has to be caught
here — without ever renaming a technical skill.
"""

from io import BytesIO

import pytest
from httpx import AsyncClient

from app.services.master_resume import master_resume_content
from app.services.profile_i18n import localize_term
from app.services.resume_latex import render_resume_latex
from app.services.resume_pdf import render_resume_pdf
from app.services.resume_text import render_resume_text

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - depends on which lib is installed
    from PyPDF2 import PdfReader


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)


class _FakeProfile:
    """Stand-in for the ORM row; localize_profile only reads attributes."""

    def __init__(self, **kwargs):
        self.id = None
        self.user_id = None
        self.headline = kwargs.get("headline", "")
        self.summary = kwargs.get("summary", "")
        self.contact_info = kwargs.get("contact_info", {})
        self.skills = kwargs.get("skills", [])
        self.experience = kwargs.get("experience", [])
        self.education = kwargs.get("education", [])
        self.certifications = kwargs.get("certifications", [])
        self.languages = kwargs.get("languages", [])
        self.screening_answers = []
        self.translations = kwargs.get("translations", {})


def _profile(**overrides):
    base = dict(
        headline="Backend Engineer | C#, AWS",
        summary="Engineer with C# and AWS experience.",
        skills=[
            {"name": "ASP.NET"},
            {"name": "Comunicacion"},
            {"name": "Liderazgo"},
            {"name": "Leadership"},
            {"name": "SpringBoot"},
        ],
        experience=[
            {
                "company": "PUCMM",
                "title": "Software Developer",
                "start_date": "2022-01",
                "end_date": None,
                "location": "Santiago, RD",
                "bullets": ["Built apps in C#.", "   "],
                "skills_used": ["C#"],
            }
        ],
        education=[
            {
                "institution": "PUCMM",
                "degree": "Bachelor's Degree in Computer Science Engineering",
                "field": "Computer Science",
                "start_date": "2020",
                "end_date": None,
            }
        ],
        certifications=[{"name": "AWS Cloud Practitioner", "issuer": "Amazon", "date": "2024"}],
        # Exactly how the real profile stores them: no accent, stray spaces.
        languages=[{"name": "Espanol", "level": "nativo"}, {"name": "English ", "level": "Native "}],
        translations={
            "es": {
                "headline": "Ingeniero Backend | C#, AWS",
                "summary": "Ingeniero con experiencia en C# y AWS.",
                "experience": [
                    {"title": "Desarrollador de Software", "bullets": ["Construí apps en C#."]}
                ],
                "education": [
                    {
                        "degree": "Licenciatura en Ingeniería en Ciencias de la Computación",
                        "field": "Ciencias de la Computación",
                    }
                ],
            }
        },
    )
    base.update(overrides)
    return _FakeProfile(**base)


# --- glossary ----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,english,spanish",
    [
        ("Comunicacion", "Communication", "Comunicación"),
        ("comunicación", "Communication", "Comunicación"),
        ("Leadership", "Leadership", "Liderazgo"),
        ("  Trabajo   en equipo ", "Teamwork", "Trabajo en equipo"),
        ("Integracion de APIs", "API Integration", "Integración de APIs"),
        # Ordinary-word skills too: without these the Spanish CV printed
        # "Liderazgo, Comunicación, Team coordination, Technical documentation".
        ("Team coordination", "Team Coordination", "Coordinación de equipos"),
        ("Technical documentation", "Technical Documentation", "Documentación técnica"),
        ("Data pipelines", "Data Pipelines", "Pipelines de datos"),
        ("SpringBoot", "Spring Boot", "Spring Boot"),
        ("Espanol", "Spanish", "Español"),
        ("English ", "English", "Inglés"),
        ("nativo", "Native", "Nativo"),
    ],
)
def test_language_bound_terms_are_translated(raw, english, spanish):
    assert localize_term(raw, "en") == english
    assert localize_term(raw, "es") == spanish


@pytest.mark.parametrize("technical", ["ASP.NET", "C#", "SQL Server", "Docker", "Javalin", "Testing", "C1"])
def test_technical_skills_are_never_renamed(technical):
    """The skills taxonomy's canonical name for "ASP.NET" is ".NET". Printing
    that instead would delete the exact keyword an ATS filters on — a
    regression nobody would notice by reading the CV."""
    assert localize_term(technical, "en") == technical
    assert localize_term(technical, "es") == technical


def test_empty_terms_stay_empty():
    assert localize_term(None, "en") == ""
    assert localize_term("   ", "es") == ""


# --- content -----------------------------------------------------------------


def test_master_content_carries_the_whole_profile_in_each_language():
    en = master_resume_content(_profile(), "en")
    es = master_resume_content(_profile(), "es")

    assert en["headline"] == "Backend Engineer | C#, AWS"
    assert es["headline"] == "Ingeniero Backend | C#, AWS"
    assert es["summary"] == "Ingeniero con experiencia en C# y AWS."
    assert es["experience"][0]["title"] == "Desarrollador de Software"
    assert es["experience"][0]["bullets"] == ["Construí apps en C#."]
    # Facts do not change with the language.
    assert en["experience"][0]["start_date"] == es["experience"][0]["start_date"] == "2022-01"
    assert en["certifications"] == es["certifications"] == [
        {"name": "AWS Cloud Practitioner", "issuer": "Amazon", "date": "2024"}
    ]


def test_skills_are_translated_and_deduplicated_but_technical_ones_kept():
    assert master_resume_content(_profile(), "en")["skills"] == [
        "ASP.NET",
        "Communication",
        "Leadership",
        "Spring Boot",
    ]
    assert master_resume_content(_profile(), "es")["skills"] == [
        "ASP.NET",
        "Comunicación",
        "Liderazgo",
        "Spring Boot",
    ]


def test_blank_bullets_are_dropped():
    assert master_resume_content(_profile(), "en")["experience"][0]["bullets"] == ["Built apps in C#."]


def test_spoken_languages_are_cleaned_and_translated():
    assert master_resume_content(_profile(), "en")["languages"] == [
        {"name": "Spanish", "level": "Native"},
        {"name": "English", "level": "Native"},
    ]
    assert master_resume_content(_profile(), "es")["languages"] == [
        {"name": "Español", "level": "Nativo"},
        {"name": "Inglés", "level": "Nativo"},
    ]


# --- renderers ---------------------------------------------------------------


def _render_all(content, language):
    kwargs = dict(
        full_name="Juan Alvarado",
        contact_info={"phone": "+1 829-619-8930"},
        content=content,
        language=language,
        email="juan@example.com",
    )
    return {
        "pdf": _pdf_text(render_resume_pdf(**kwargs)),
        "tex": render_resume_latex(**kwargs),
        "txt": render_resume_text(title="Juan Alvarado", content=content, language=language),
    }


@pytest.mark.parametrize(
    "language,headings,headline_start",
    [
        ("en", ("CERTIFICATIONS", "LANGUAGES"), "Backend Engineer"),
        ("es", ("CERTIFICACIONES", "IDIOMAS"), "Ingeniero Backend"),
    ],
)
def test_master_sections_appear_in_every_format(language, headings, headline_start):
    content = master_resume_content(_profile(), language)
    for fmt, rendered in _render_all(content, language).items():
        for heading in headings:
            assert heading in rendered, f"{heading} missing from the {fmt} export"
        assert headline_start in rendered, f"headline missing from the {fmt} export"


def test_a_tailored_cv_is_unchanged_by_the_master_only_sections():
    """Tailored content has no headline, certifications or languages, and
    must render exactly as it did before those sections existed."""
    tailored = {"summary": "Engineer.", "skills": ["C#"], "experience": [], "education": []}
    for fmt, rendered in _render_all(tailored, "en").items():
        for heading in ("CERTIFICATIONS", "LANGUAGES"):
            assert heading not in rendered, f"the {fmt} export grew a {heading} heading"

    tex = render_resume_latex(full_name="Juan", contact_info={}, content=tailored, email="j@x.com")
    assert "\\begin{center}\n{\\LARGE\\bfseries Juan}\\\\[4pt]\n{\\small j@x.com}\n\\end{center}" in tex


def test_text_export_no_longer_repeats_the_field_the_degree_names():
    """The PDF and LaTeX exports already applied this rule; the plain-text one
    had missed it and printed "...Engineering in Computer Science"."""
    content = master_resume_content(_profile(), "en")
    text = render_resume_text(title="Juan", content=content, language="en")
    assert "Engineering in Computer Science" not in text
    assert "Bachelor's Degree in Computer Science Engineering" in text


# --- endpoints -----------------------------------------------------------------

PROFILE_PAYLOAD = {
    "headline": "Backend Engineer",
    "summary": "Engineer with C# experience.",
    "contact_info": {"phone": "+1 829-619-8930", "city": "Santiago"},
    "skills": [{"name": "C#"}, {"name": "Comunicacion"}],
    "experience": [
        {
            "company": "PUCMM",
            "title": "Software Developer",
            "start_date": "2022-01",
            "bullets": ["Built apps in C#."],
            "skills_used": ["C#"],
        }
    ],
    "education": [{"institution": "PUCMM", "degree": "BSc", "field": "Computer Science", "start_date": "2020"}],
    "languages": [{"name": "Espanol", "level": "nativo"}],
    "translations": {
        "es": {"headline": "Ingeniero Backend", "summary": "Ingeniero con experiencia en C#."}
    },
}

EXPORT_PATHS = ("/profile/export", "/profile/export/pdf", "/profile/export/tex")


@pytest.mark.asyncio
async def test_exports_require_authentication(async_client: AsyncClient):
    for path in EXPORT_PATHS:
        response = await async_client.get(path)
        assert response.status_code == 401, path


@pytest.mark.asyncio
async def test_exports_404_before_a_profile_exists(async_client: AsyncClient, user_and_headers):
    _user, headers = user_and_headers
    for path in EXPORT_PATHS:
        response = await async_client.get(path, headers=headers)
        assert response.status_code == 404, path


@pytest.mark.asyncio
async def test_master_cv_downloads_in_each_format_and_language(
    async_client: AsyncClient, user_and_headers
):
    user, headers = user_and_headers
    saved = await async_client.put("/profile", json=PROFILE_PAYLOAD, headers=headers)
    assert saved.status_code == 200, saved.text

    pdf = await async_client.get("/profile/export/pdf", params={"language": "es"}, headers=headers)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert "cv-maestro-es.pdf" in pdf.headers["content-disposition"]
    text = _pdf_text(pdf.content)
    assert "Ingeniero Backend" in text
    assert "RESUMEN PROFESIONAL" in text and "IDIOMAS" in text
    assert "Español — Nativo" in text
    # An ATS keys its candidate record on the email address.
    assert user.email in text

    tex = await async_client.get("/profile/export/tex", params={"language": "en"}, headers=headers)
    assert tex.status_code == 200
    assert "\\documentclass" in tex.text and "[english]{babel}" in tex.text
    assert "cv-maestro-en.tex" in tex.headers["content-disposition"]
    assert "Communication" in tex.text and "Comunicacion" not in tex.text

    txt = await async_client.get("/profile/export", params={"language": "es"}, headers=headers)
    assert txt.status_code == 200
    assert "HABILIDADES" in txt.text and "Comunicación" in txt.text


@pytest.mark.asyncio
async def test_unknown_language_falls_back_instead_of_failing(async_client: AsyncClient, user_and_headers):
    _user, headers = user_and_headers
    await async_client.put("/profile", json=PROFILE_PAYLOAD, headers=headers)

    response = await async_client.get("/profile/export", params={"language": "fr"}, headers=headers)
    assert response.status_code == 200
    assert "SKILLS" in response.text
    assert "cv-maestro-en.txt" in response.headers["content-disposition"]
