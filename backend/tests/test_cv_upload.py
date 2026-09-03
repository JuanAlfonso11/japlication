import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services import cv_upload

SAMPLE_RESUME_TEXT = """Camila Reyes
Backend Engineer

camila.reyes@example.com | +1 555-123-4567
linkedin.com/in/camilareyes | github.com/camilareyes

Summary
Backend engineer with 4 years building APIs in Python and C#.

Experience
Nimbus Software — Backend Engineer (2022-2023)
- Built REST APIs handling 2M+ requests/day.

Skills
Python, SQL, Docker, REST APIs
"""


def test_extract_text_from_pdf_rejects_garbage_bytes():
    with pytest.raises(HTTPException) as exc_info:
        cv_upload.extract_text_from_pdf(b"not a real pdf")
    assert exc_info.value.status_code == 422


def test_heuristic_parse_extracts_contact_links_and_skills():
    result = cv_upload._heuristic_parse(SAMPLE_RESUME_TEXT)
    assert result["generated_by"] == "heuristic"
    profile = result["profile"]
    assert profile["contact_info"]["linkedin"] == "linkedin.com/in/camilareyes" or "linkedin.com/in/camilareyes" in (
        profile["contact_info"]["linkedin"] or ""
    )
    assert profile["contact_info"]["github"]
    skill_names = {s["name"] for s in profile["skills"]}
    assert "Python" in skill_names
    assert "Docker" in skill_names
    # The heuristic path never guesses at structured experience/education.
    assert profile["experience"] == []
    assert profile["education"] == []
    assert result["warnings"]


def test_heuristic_parse_finds_email_separately_from_profile():
    result = cv_upload._heuristic_parse(SAMPLE_RESUME_TEXT)
    assert result["email_found"] == "camila.reyes@example.com"


def test_heuristic_parse_headline_from_first_line():
    result = cv_upload._heuristic_parse("Senior Backend Engineer\n\nRest of resume...")
    assert result["profile"]["headline"] == "Senior Backend Engineer"


def test_parse_cv_uses_ai_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")

    fake_profile = {
        "headline": "Backend Engineer",
        "summary": "Backend engineer with 4 years of experience.",
        "contact_info": {"phone": None, "city": None, "country": None, "linkedin": None, "github": None, "portfolio": None},
        "skills": [{"name": "Python", "category": None, "level": None, "years_experience": 4}],
        "experience": [
            {
                "company": "Nimbus Software",
                "title": "Backend Engineer",
                "start_date": "2022",
                "end_date": "2023",
                "location": None,
                "bullets": ["Built REST APIs handling 2M+ requests/day."],
                "skills_used": ["Python"],
            }
        ],
        "education": [],
        "certifications": [],
        "languages": [],
    }

    monkeypatch.setattr(cv_upload, "_try_ai_parse", lambda text: {"profile": fake_profile, "generated_by": "ai", "warnings": [], "email_found": None})
    monkeypatch.setattr(cv_upload, "extract_text_from_pdf", lambda file_bytes: SAMPLE_RESUME_TEXT)

    result = cv_upload.parse_cv(b"irrelevant-bytes")
    assert result["generated_by"] == "ai"
    assert result["profile"]["experience"][0]["company"] == "Nimbus Software"


def test_parse_cv_falls_back_to_heuristic_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(cv_upload, "extract_text_from_pdf", lambda file_bytes: SAMPLE_RESUME_TEXT)

    result = cv_upload.parse_cv(b"irrelevant-bytes")
    assert result["generated_by"] == "heuristic"


def test_try_ai_parse_returns_none_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    assert cv_upload._try_ai_parse(SAMPLE_RESUME_TEXT) is None
