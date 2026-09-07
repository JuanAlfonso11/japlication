from types import SimpleNamespace

from app.services.interview_prep import build_interview_prep


def profile(experience=None, headline="Backend Engineer"):
    return SimpleNamespace(
        headline=headline,
        summary="",
        experience=experience
        if experience is not None
        else [
            {
                "company": "Acme",
                "title": "Backend Engineer",
                "bullets": [
                    "Migré el pipeline de datos a Kubernetes reduciendo el costo 30%",
                    "Diseñé la API de pagos en Python",
                ],
            }
        ],
    )


def job(requirements=None, title="Senior Backend Engineer", company="Globex"):
    return SimpleNamespace(
        title=title,
        company=company,
        description="Buscamos un backend senior.",
        requirements=requirements if requirements is not None else ["5+ años en Python"],
    )


def test_asks_about_skills_the_candidate_actually_has():
    result = build_interview_prep(profile(), job(), ["Kubernetes"], [])
    kubernetes = [q for q in result["questions"] if "Kubernetes" in q["question"]]
    assert kubernetes, "debería preguntar por una skill que sí tiene"
    assert kubernetes[0]["category"] == "tecnica"


def test_talking_points_come_from_the_candidates_own_bullets():
    """The whole point: the answer material must be traceable to something
    the user actually wrote, never generated prose."""
    result = build_interview_prep(profile(), job(), ["Kubernetes"], [])
    kubernetes = next(q for q in result["questions"] if "Kubernetes" in q["question"])
    assert any("pipeline de datos" in point for point in kubernetes["talking_points"])
    assert any("Acme" in point for point in kubernetes["talking_points"])


def test_a_missing_skill_becomes_a_gap_question_and_never_a_fake_answer():
    result = build_interview_prep(profile(), job(), [], ["Rust"])
    gap = next(q for q in result["questions"] if q["category"] == "brecha")
    assert "Rust" in gap["question"]
    joined = " ".join(gap["talking_points"]).lower()
    assert "no inventes" in joined
    # It must not claim any Rust experience on the candidate's behalf.
    assert "años de experiencia en rust" not in joined


def test_a_claimed_skill_with_no_evidence_says_so_instead_of_inventing_one():
    bare = profile(experience=[{"company": "Acme", "title": "Dev", "bullets": ["Hice cosas"]}])
    result = build_interview_prep(bare, job(), ["Kubernetes"], [])
    kubernetes = next(q for q in result["questions"] if "Kubernetes" in q["question"])
    joined = " ".join(kubernetes["talking_points"]).lower()
    assert "prepara un ejemplo" in joined


def test_pulls_questions_from_the_postings_own_requirements():
    result = build_interview_prep(profile(), job(requirements=["Experiencia liderando equipos"]), [], [])
    assert any("liderando equipos" in q["question"] for q in result["questions"])


def test_always_includes_the_why_this_company_question():
    result = build_interview_prep(profile(), job(company="Globex"), [], [])
    assert any(q["category"] == "empresa" and "Globex" in q["question"] for q in result["questions"])


def test_works_with_an_empty_profile_and_a_bare_job():
    empty = SimpleNamespace(headline="", summary="", experience=[])
    result = build_interview_prep(empty, job(requirements=[]), [], [])
    assert result["questions"], "aun sin datos debe dar algo accionable"
    assert result["generated_by"] == "manual"


def test_caps_the_sheet_at_a_readable_length():
    """A prep sheet you read on the way to the interview; twenty questions
    is a document nobody opens."""
    result = build_interview_prep(
        profile(),
        job(requirements=[f"Requisito {i}" for i in range(10)]),
        [f"Skill{i}" for i in range(10)],
        [f"Falta{i}" for i in range(10)],
    )
    assert len(result["questions"]) <= 8


def test_falls_back_to_rules_when_no_api_key_is_configured():
    result = build_interview_prep(profile(), job(), ["Kubernetes"], [])
    assert result["generated_by"] == "manual"
