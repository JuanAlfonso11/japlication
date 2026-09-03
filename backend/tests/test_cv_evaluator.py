from types import SimpleNamespace

from app.core.config import settings
from app.services import cv_evaluator
from app.services.cv_evaluator import evaluate_cv


def make_profile(**overrides):
    defaults = dict(
        headline="Senior Backend Engineer",
        summary="Backend engineer with 5 years building APIs and distributed systems for fintech products.",
        contact_info={"linkedin": "https://linkedin.com/in/example"},
        skills=[
            {"name": "Python", "years_experience": 5},
            {"name": "PostgreSQL", "years_experience": 4},
            {"name": "AWS", "years_experience": 3},
            {"name": "Docker", "years_experience": 2},
            {"name": "REST APIs", "years_experience": 5},
        ],
        experience=[
            {
                "company": "Acme Corp",
                "title": "Backend Engineer",
                "start_date": "2019-01",
                "end_date": "2023-01",
                "bullets": [
                    "Reduced API latency by 40% by redesigning the caching layer.",
                    "Led a team of 3 engineers to migrate 12 services to Docker, cutting deploy time by 60%.",
                ],
                "skills_used": ["Python", "PostgreSQL", "Docker"],
            }
        ],
        education=[{"institution": "State University", "degree": "BSc Computer Science"}],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_empty_profile_scores_low_and_flags_everything():
    profile = make_profile(
        headline="", summary="", contact_info={}, skills=[], experience=[], education=[]
    )
    result = evaluate_cv(profile)

    assert result["overall_score"] < 30
    assert result["band"] == "Necesita trabajo"
    messages = " ".join(i["message"] for i in result["top_issues"])
    assert "titular profesional" in messages
    assert "resumen profesional" in messages
    assert "experiencia laboral" in messages
    assert "habilidades registradas" in messages


def test_well_formed_profile_scores_high():
    profile = make_profile()
    result = evaluate_cv(profile)

    assert result["overall_score"] >= 75
    assert result["band"] in ("Sólido", "Excelente")
    assert result["strengths"]


def test_impact_flags_unquantified_and_weak_bullets():
    profile = make_profile(
        experience=[
            {
                "company": "Acme Corp",
                "title": "Backend Engineer",
                "bullets": [
                    "Responsable de mantenimiento del sistema.",
                    "Encargado de tareas variadas.",
                    "Trabajé en el equipo backend.",
                ],
                "skills_used": [],
            }
        ]
    )
    result = evaluate_cv(profile)
    impact_issues = " ".join(i["message"] for i in result["categories"]["impact"]["issues"])
    assert "métricas" in impact_issues
    assert "frases pasivas" in impact_issues
    assert result["categories"]["impact"]["score"] < 50


def test_experience_entry_without_bullets_is_flagged():
    profile = make_profile(
        experience=[{"company": "Acme Corp", "title": "Backend Engineer", "bullets": []}]
    )
    result = evaluate_cv(profile)
    messages = " ".join(i["message"] for i in result["categories"]["impact"]["issues"])
    assert "Acme Corp" in messages
    assert "no tiene logros" in messages


def test_skills_without_years_are_flagged():
    profile = make_profile(skills=[{"name": "Python"}, {"name": "SQL", "years_experience": 0}])
    result = evaluate_cv(profile)
    messages = " ".join(i["message"] for i in result["categories"]["skills_breadth"]["issues"])
    assert "años de experiencia" in messages


def test_skills_used_but_missing_from_skills_list_is_flagged():
    profile = make_profile(
        skills=[{"name": "Python", "years_experience": 5}],
        experience=[
            {
                "company": "Acme Corp",
                "title": "Backend Engineer",
                "bullets": ["Built things with Kubernetes and Python."],
                "skills_used": ["Python", "Kubernetes"],
            }
        ],
    )
    result = evaluate_cv(profile)
    messages = " ".join(i["message"] for i in result["categories"]["skills_breadth"]["issues"])
    assert "Kubernetes" in messages
    # Python is already in the skills list, so it should not be called out as missing.
    assert "Python" not in messages


def test_ats_safety_flags_emoji_long_bullets_and_bad_dates():
    profile = make_profile(
        headline="Backend Engineer 🚀",
        experience=[
            {
                "company": "Acme Corp",
                "title": "Backend Engineer",
                "start_date": "Jan 2019",
                "bullets": ["x" * 250],
            }
        ],
    )
    result = evaluate_cv(profile)
    messages = " ".join(i["message"] for i in result["categories"]["ats_safety"]["issues"])
    assert "emojis" in messages
    assert "muy largos" in messages
    assert "Acme Corp" in messages
    assert result["categories"]["ats_safety"]["score"] < 100


def test_summary_falls_back_to_deterministic_sentence_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    profile = make_profile(headline="")
    result = evaluate_cv(profile)
    assert result["summary_generated_by"] == "manual"
    assert result["summary"]


def test_ai_summary_used_when_available(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(cv_evaluator, "_try_ai_summary", lambda evaluation: "Texto generado por IA.")
    profile = make_profile()
    result = evaluate_cv(profile)
    assert result["summary_generated_by"] == "ai"
    assert result["summary"] == "Texto generado por IA."


def test_overall_score_is_weighted_average_of_categories():
    profile = make_profile()
    result = evaluate_cv(profile)
    expected = round(
        sum(
            result["categories"][cat]["score"] * weight
            for cat, weight in cv_evaluator.CATEGORY_WEIGHTS.items()
        ),
        1,
    )
    assert result["overall_score"] == expected
