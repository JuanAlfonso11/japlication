from app.services.profile_improver import improve_profile

PROFILE = {
    "headline": "Software Developer",
    "summary": "",
    "contact_info": {"city": "Santiago", "country": "Dominican Republic"},
    "skills": [{"name": "C#", "category": "language", "level": "advanced", "years_experience": 3}],
    "experience": [
        {
            "company": "Acme",
            "title": "Backend Developer",
            "start_date": "2022-01",
            "end_date": None,
            "location": "Remote",
            "bullets": ["built rest apis for internal tools", "  maintained ci/cd pipelines  "],
            "skills_used": ["C#"],
        }
    ],
    "education": [{"institution": "PUCMM", "degree": "Ingenieria", "field": "Software", "start_date": "2018", "end_date": "2022"}],
    "certifications": [],
    "languages": [{"name": "Spanish", "level": "native"}],
}


def test_improve_profile_writes_missing_summary_without_ai(monkeypatch):
    import app.services.profile_improver as mod

    monkeypatch.setattr(mod.settings, "ANTHROPIC_API_KEY", None)
    result = improve_profile(PROFILE)

    assert result["generated_by"] == "manual"
    assert result["profile"]["summary"]  # was empty, now filled in
    assert "Software Developer" in result["profile"]["summary"]
    assert len(result["change_log"]) > 0


def test_improve_profile_never_touches_structured_fields(monkeypatch):
    import app.services.profile_improver as mod

    monkeypatch.setattr(mod.settings, "ANTHROPIC_API_KEY", None)
    result = improve_profile(PROFILE)

    assert result["profile"]["contact_info"] == PROFILE["contact_info"]
    assert result["profile"]["skills"] == PROFILE["skills"]
    assert result["profile"]["education"] == PROFILE["education"]
    assert result["profile"]["languages"] == PROFILE["languages"]


def test_improve_profile_keeps_bullet_count_and_facts(monkeypatch):
    import app.services.profile_improver as mod

    monkeypatch.setattr(mod.settings, "ANTHROPIC_API_KEY", None)
    result = improve_profile(PROFILE)

    entry = result["profile"]["experience"][0]
    assert entry["company"] == "Acme"
    assert entry["title"] == "Backend Developer"
    assert len(entry["bullets"]) == 2
    assert entry["bullets"][0][0].isupper()


def test_improve_profile_falls_back_when_anthropic_unavailable(monkeypatch):
    import app.services.profile_improver as mod

    monkeypatch.setattr(mod.settings, "ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(mod, "_try_anthropic_improve", lambda profile: None)
    result = improve_profile(PROFILE)

    assert result["generated_by"] == "manual"
