"""Tests for the bilingual profile: one profile, a CV in either language.

The invariant worth protecting here is asymmetric. Getting the *language*
wrong on a CV is embarrassing but visible the moment you open the PDF.
Getting the *facts* wrong -- a translation that quietly drops a bullet, or
a half-finished translation that blanks the summary -- is invisible until a
recruiter reads a CV that is missing half your experience. So most of these
tests are about fallback and content preservation, not about wording.
"""

import pytest
from httpx import AsyncClient

from app.services.profile_i18n import (
    BASE_LANGUAGE,
    detect_language,
    labels_for,
    localize_profile,
    normalize_language,
    translation_status,
)


class _FakeProfile:
    """Minimal stand-in for the ORM row. Deliberately not the real model:
    these functions must work on anything with the right attributes, which
    is what lets LocalizedProfile be fed back into them."""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.user_id = kwargs.get("user_id")
        self.headline = kwargs.get("headline")
        self.summary = kwargs.get("summary")
        self.contact_info = kwargs.get("contact_info", {})
        self.skills = kwargs.get("skills", [])
        self.experience = kwargs.get("experience", [])
        self.education = kwargs.get("education", [])
        self.certifications = kwargs.get("certifications", [])
        self.languages = kwargs.get("languages", [])
        self.screening_answers = kwargs.get("screening_answers", [])
        self.translations = kwargs.get("translations", {})


def _profile(**overrides):
    base = dict(
        headline="Backend Engineer",
        summary="Engineer with C# and AWS experience.",
        skills=[{"name": "C#"}, {"name": "AWS"}],
        experience=[
            {
                "company": "PUCMM - Academic Projects",
                "title": "Software Developer",
                "start_date": "2021-01",
                "end_date": None,
                "location": "Santiago, RD",
                "bullets": ["Built mobile apps in C# with Xamarin."],
                "skills_used": ["C#"],
            }
        ],
        education=[
            {
                "institution": "PUCMM",
                "degree": "Bachelor's Degree in Computer Science Engineering",
                "field": "Computer Science",
                "start_date": "2018",
                "end_date": "2023",
            }
        ],
    )
    base.update(overrides)
    return _FakeProfile(**base)


# --- normalize_language ----------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("es", "es"),
        ("ES", "es"),
        ("es-DO", "es"),  # what a Dominican browser actually sends
        ("es_419", "es"),
        ("en-US", "en"),
        ("fr", BASE_LANGUAGE),  # unsupported -> base, never an error
        ("", BASE_LANGUAGE),
        (None, BASE_LANGUAGE),
    ],
)
def test_normalize_language_accepts_real_locale_tags(raw, expected):
    assert normalize_language(raw) == expected


# --- detect_language -------------------------------------------------------


def test_detects_english_and_spanish_postings():
    english = (
        "We are looking for a backend engineer to join our team. You will work "
        "with our platform and be responsible for the API."
    )
    spanish = (
        "Buscamos un ingeniero de backend para unirse a nuestro equipo de "
        "desarrollo. Se requiere experiencia con APIs y bases de datos."
    )
    assert detect_language(english) == "en"
    assert detect_language(spanish) == "es"


def test_detect_language_falls_back_on_unusable_input():
    """An empty or symbol-only description must not raise or coin a third
    language: the caller uses this to pick a CV, so it always needs an
    answer it can render."""
    assert detect_language(None) == BASE_LANGUAGE
    assert detect_language("") == BASE_LANGUAGE
    assert detect_language("!!! ### 42 ###") == BASE_LANGUAGE


# --- localize_profile ------------------------------------------------------


def test_base_language_returns_the_profile_unchanged():
    profile = _profile()
    localized = localize_profile(profile, "en")
    assert localized.headline == "Backend Engineer"
    assert localized.experience[0]["bullets"] == ["Built mobile apps in C# with Xamarin."]


def test_translation_replaces_prose_and_keeps_facts():
    profile = _profile(
        translations={
            "es": {
                "headline": "Ingeniero Backend",
                "summary": "Ingeniero con experiencia en C# y AWS.",
                "experience": [
                    {
                        "title": "Desarrollador de Software",
                        "bullets": ["Construí apps móviles en C# con Xamarin."],
                    }
                ],
            }
        }
    )
    es = localize_profile(profile, "es")

    assert es.headline == "Ingeniero Backend"
    assert es.experience[0]["title"] == "Desarrollador de Software"
    assert es.experience[0]["bullets"] == ["Construí apps móviles en C# con Xamarin."]

    # Facts survive untouched: dates, skills_used, and the company that was
    # not given a translation.
    assert es.experience[0]["start_date"] == "2021-01"
    assert es.experience[0]["skills_used"] == ["C#"]
    assert es.experience[0]["company"] == "PUCMM - Academic Projects"


def test_partial_translation_falls_back_field_by_field():
    """The failure this guards against: a half-finished Spanish version
    exporting a CV with an empty summary. Untranslated fields must show the
    base text, not a hole."""
    profile = _profile(translations={"es": {"headline": "Ingeniero Backend"}})
    es = localize_profile(profile, "es")

    assert es.headline == "Ingeniero Backend"
    assert es.summary == "Engineer with C# and AWS experience."
    assert es.experience[0]["bullets"] == ["Built mobile apps in C# with Xamarin."]


def test_blank_strings_and_empty_lists_do_not_erase_content():
    """A cleared textarea round-trips as "" — that means "not translated",
    not "delete my summary"."""
    profile = _profile(
        translations={"es": {"headline": "   ", "summary": "", "experience": [{"bullets": []}]}}
    )
    es = localize_profile(profile, "es")

    assert es.headline == "Backend Engineer"
    assert es.summary == "Engineer with C# and AWS experience."
    assert es.experience[0]["bullets"] == ["Built mobile apps in C# with Xamarin."]


def test_translation_shorter_than_the_base_list_keeps_the_extra_entries():
    """Adding a job without translating it yet must not drop it from the
    Spanish CV — the entry appears in the base language instead."""
    profile = _profile(
        experience=[
            {"company": "A", "title": "Dev", "bullets": ["First role."]},
            {"company": "B", "title": "Lead", "bullets": ["Second role."]},
        ],
        translations={"es": {"experience": [{"title": "Desarrollador", "bullets": ["Primer puesto."]}]}},
    )
    es = localize_profile(profile, "es")

    assert len(es.experience) == 2
    assert es.experience[0]["bullets"] == ["Primer puesto."]
    assert es.experience[1]["bullets"] == ["Second role."]


def test_unknown_language_uses_the_base_rather_than_an_empty_cv():
    profile = _profile(translations={"es": {"headline": "Ingeniero Backend"}})
    assert localize_profile(profile, "fr").headline == "Backend Engineer"


# --- translation_status ----------------------------------------------------


def test_status_reports_what_is_missing():
    profile = _profile(translations={"es": {"headline": "Ingeniero Backend"}})
    status = translation_status(profile)

    assert status["en"]["is_base"] is True
    assert status["en"]["complete"] is True

    assert status["es"]["complete"] is False
    assert "summary" in status["es"]["missing"]
    assert "experience[0].bullets" in status["es"]["missing"]
    assert "headline" not in status["es"]["missing"]


def test_status_complete_when_everything_is_translated():
    profile = _profile(
        translations={
            "es": {
                "headline": "Ingeniero Backend",
                "summary": "Ingeniero con experiencia en C# y AWS.",
                "experience": [{"bullets": ["Construí apps móviles."]}],
            }
        }
    )
    assert translation_status(profile)["es"]["complete"] is True


# --- labels ----------------------------------------------------------------


def test_cv_labels_differ_per_language_and_cover_every_section():
    en, es = labels_for("en"), labels_for("es")
    assert set(en) == set(es), "a label added to one language must exist in both"
    for key in ("summary", "skills", "experience", "education", "present"):
        assert en[key] != es[key], f"{key} is not actually translated"


# --- end to end through the API -------------------------------------------


@pytest.mark.asyncio
async def test_generate_cv_in_each_language(
    async_client: AsyncClient, user_and_headers, force_offline_adapter
):
    """The whole point, exercised through the real endpoints: one profile,
    two CVs, and a PDF for each that carries that language's headers.

    Pinned to the rule-based adapter, which copies the profile's prose
    verbatim — that is what makes "the Spanish CV contains the Spanish
    summary" checkable at all. With a live key the model rewrites the
    wording and there is nothing exact left to assert, so this test would
    pass or fail depending on the environment rather than on the code.
    """
    _user, headers = user_and_headers

    profile_payload = {
        "headline": "Backend Engineer",
        "summary": "Engineer with C# and AWS experience.",
        "skills": [{"name": "C#"}],
        "experience": [
            {
                "company": "PUCMM",
                "title": "Software Developer",
                "start_date": "2021-01",
                "bullets": ["Built mobile apps in C# with Xamarin."],
                "skills_used": ["C#"],
            }
        ],
        "education": [{"institution": "PUCMM", "degree": "BSc", "field": "Computer Science"}],
        "translations": {
            "es": {
                "headline": "Ingeniero Backend",
                "summary": "Ingeniero con experiencia en C# y AWS.",
                "experience": [
                    {
                        "title": "Desarrollador de Software",
                        "bullets": ["Construí apps móviles en C# con Xamarin."],
                    }
                ],
            }
        },
    }
    response = await async_client.put("/profile", json=profile_payload, headers=headers)
    assert response.status_code == 200, response.text

    languages = (await async_client.get("/profile/languages", headers=headers)).json()
    by_code = {entry["code"]: entry for entry in languages}
    assert by_code["es"]["complete"] is True

    job_payload = {
        "title": "Backend Engineer",
        "company": "Acme",
        "description": "We are looking for a backend engineer to join the team.",
        "location": "Remote",
        "skills_required": [{"name": "C#", "importance": "required"}],
    }
    job = (await async_client.post("/jobs", json=job_payload, headers=headers)).json()

    generated = {}
    for language in ("en", "es"):
        response = await async_client.post(
            f"/jobs/{job['id']}/resume", json={"language": language}, headers=headers
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["language"] == language
        generated[language] = body

    assert generated["en"]["content"]["summary"].startswith("Engineer with")
    assert generated["es"]["content"]["summary"].startswith("Ingeniero con")
    assert generated["es"]["content"]["experience"][0]["title"] == "Desarrollador de Software"

    # The facts are identical across languages — only the prose changed.
    assert (
        generated["en"]["content"]["experience"][0]["start_date"]
        == generated["es"]["content"]["experience"][0]["start_date"]
    )

    for language, version in generated.items():
        response = await async_client.get(
            f"/resume-versions/{version['id']}/export", headers=headers
        )
        assert response.status_code == 200
        text = response.text
        assert ("RESUMEN PROFESIONAL" in text) is (language == "es")
        assert ("SUMMARY" in text) is (language == "en")

        response = await async_client.get(
            f"/resume-versions/{version['id']}/export/pdf", headers=headers
        )
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF")
        assert f"resume-{language}-" in response.headers["content-disposition"]


@pytest.fixture
def force_offline_adapter(monkeypatch):
    """Pins resume generation to the deterministic rule-based path.

    conftest.py already clears the key for the whole suite, so this is
    belt-and-braces: it keeps these tests correct even if someone runs them
    with a key in the environment, and it documents at the point of use
    which of the two adapters is being asserted on.
    """
    from app.services import resume_adapter

    monkeypatch.setattr(resume_adapter, "get_anthropic_client", lambda: None)


@pytest.mark.asyncio
async def test_language_defaults_to_the_language_of_the_posting(
    async_client: AsyncClient, user_and_headers, force_offline_adapter
):
    """Omitting `language` should not silently mean English: a Spanish ad
    should get a Spanish CV without the user having to ask."""
    _user, headers = user_and_headers

    await async_client.put(
        "/profile",
        json={
            "headline": "Backend Engineer",
            "summary": "Engineer with C# experience.",
            "skills": [{"name": "C#"}],
            "experience": [],
            "translations": {"es": {"headline": "Ingeniero Backend", "summary": "Ingeniero."}},
        },
        headers=headers,
    )

    spanish_job = (
        await async_client.post(
            "/jobs",
            json={
                "title": "Ingeniero Backend",
                "company": "Acme",
                "description": (
                    "Buscamos un ingeniero de backend para unirse a nuestro equipo de "
                    "desarrollo. Se requiere experiencia con bases de datos y APIs."
                ),
                "location": "Remoto",
                "skills_required": [{"name": "C#", "importance": "required"}],
            },
            headers=headers,
        )
    ).json()

    response = await async_client.post(f"/jobs/{spanish_job['id']}/resume", headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["language"] == "es"


@pytest.mark.asyncio
async def test_saving_without_translations_does_not_erase_them(
    async_client: AsyncClient, user_and_headers
):
    """The installed APK predates this feature and PUTs a profile with no
    `translations` key. That must leave the Spanish CV alone instead of
    wiping it on the user's next save."""
    _user, headers = user_and_headers

    await async_client.put(
        "/profile",
        json={
            "headline": "Backend Engineer",
            "summary": "Engineer.",
            "translations": {"es": {"headline": "Ingeniero Backend", "summary": "Ingeniero."}},
        },
        headers=headers,
    )

    # Exactly what an older client sends: no `translations` key at all.
    response = await async_client.put(
        "/profile",
        json={"headline": "Backend Engineer", "summary": "Engineer, updated."},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["translations"]["es"]["headline"] == "Ingeniero Backend"

    # An explicit empty object still clears them — that is a real request.
    response = await async_client.put(
        "/profile",
        json={"headline": "Backend Engineer", "summary": "Engineer.", "translations": {}},
        headers=headers,
    )
    assert response.json()["translations"] == {}


@pytest.mark.asyncio
async def test_reuse_never_offers_a_cv_in_the_other_language(
    async_client: AsyncClient, user_and_headers
):
    """Two postings with identical skills: the Spanish CV from the first
    must not be suggested for the English second one."""
    _user, headers = user_and_headers

    await async_client.put(
        "/profile",
        json={
            "headline": "Backend Engineer",
            "summary": "Engineer with C# experience.",
            "skills": [{"name": "C#"}],
            "translations": {"es": {"headline": "Ingeniero Backend", "summary": "Ingeniero."}},
        },
        headers=headers,
    )

    skills = [{"name": "C#", "importance": "required"}]
    first = (
        await async_client.post(
            "/jobs",
            json={
                "title": "Ingeniero Backend",
                "company": "Uno",
                "description": "Buscamos un ingeniero para nuestro equipo de desarrollo.",
                "location": "Remoto",
                "skills_required": skills,
            },
            headers=headers,
        )
    ).json()
    second = (
        await async_client.post(
            "/jobs",
            json={
                "title": "Backend Engineer",
                "company": "Dos",
                "description": "We are looking for an engineer to join the team.",
                "location": "Remote",
                "skills_required": skills,
            },
            headers=headers,
        )
    ).json()

    created = await async_client.post(
        f"/jobs/{first['id']}/resume", json={"language": "es"}, headers=headers
    )
    assert created.json()["language"] == "es"

    suggestion = (
        await async_client.get(f"/jobs/{second['id']}/resume/reusable?language=en", headers=headers)
    ).json()
    assert suggestion["resume_version"] is None

    # Same skills, same language: now it IS worth reusing, which proves the
    # test above failed for the language and not because reuse is broken.
    suggestion = (
        await async_client.get(f"/jobs/{second['id']}/resume/reusable?language=es", headers=headers)
    ).json()
    assert suggestion["resume_version"] is not None
    assert suggestion["source_company"] == "Uno"


# --- cost safety -----------------------------------------------------------


def test_job_description_sent_to_the_llm_is_capped():
    """An importer that lands on a careers index page instead of a single
    posting stores a description hundreds of thousands of characters long
    (this database has a 490,000-char one). Uncapped, generating one CV for
    it becomes a ~122,000-token request — real money on a metered key, from
    one click. cover_letter_generator and interview_prep already cap at
    1,500; this proves the adapter does too."""
    from unittest.mock import patch

    from app.services import resume_adapter

    class _Job:
        title = "Backend Engineer"
        company = "Acme"
        description = "x" * 500_000
        requirements = []
        skills_required = [{"name": "C#", "importance": "required"}]

    captured = {}

    class _FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("stop here — we only need the payload")

    class _FakeClient:
        messages = _FakeMessages()

    with patch.object(resume_adapter, "get_anthropic_client", lambda: _FakeClient()):
        # Falls back to the rule-based path once the fake client raises,
        # which is exactly the behaviour every AI failure gets.
        result = resume_adapter.adapt_resume(_profile(), _Job(), "en")

    assert result["generated_by"] == "manual"
    sent = captured["messages"][0]["content"]
    assert "x" * 8000 in sent, "the description should still be sent, just bounded"
    assert "x" * 8001 not in sent, "the description was not capped"
