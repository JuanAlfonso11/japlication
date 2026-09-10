from types import SimpleNamespace

import pytest

from app.services.match_engine import (
    compute_experience_score,
    compute_match,
    compute_relevant_experience_years,
    compute_semantic_score,
    compute_technical_score,
    extract_required_years,
)


def make_profile(**overrides):
    defaults = dict(
        headline="Senior Backend Engineer",
        summary="Backend engineer focused on APIs and distributed systems.",
        skills=[
            {"name": "Python", "category": "language", "level": "advanced", "years_experience": 5},
            {"name": "PostgreSQL", "category": "database", "level": "advanced"},
            {"name": "AWS", "category": "cloud", "level": "intermediate"},
        ],
        experience=[
            {
                "company": "Acme Corp",
                "title": "Backend Engineer",
                "start_date": "2019-01",
                "end_date": "2023-01",
                "bullets": ["Built REST APIs with Python and FastAPI", "Managed PostgreSQL databases"],
                "skills_used": ["Python", "PostgreSQL", "REST APIs"],
            }
        ],
        education=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_job(**overrides):
    defaults = dict(
        title="Senior Python Backend Engineer",
        company="Widgets Inc",
        description="We need 5+ years of experience with Python and PostgreSQL.",
        seniority="senior",
        requirements=["5+ years of Python", "Experience with PostgreSQL"],
        skills_required=[
            {"name": "Python", "importance": "required"},
            {"name": "PostgreSQL", "importance": "required"},
            {"name": "Kubernetes", "importance": "nice_to_have"},
        ],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Technical score / skill overlap
# ---------------------------------------------------------------------------


class TestTechnicalScore:
    def test_full_overlap_scores_100(self):
        profile_skills = [{"name": "Python"}, {"name": "PostgreSQL"}]
        job_skills = [
            {"name": "Python", "importance": "required"},
            {"name": "PostgreSQL", "importance": "required"},
        ]
        score, matched, missing = compute_technical_score(profile_skills, job_skills)
        assert score == 100.0
        assert set(matched) == {"Python", "PostgreSQL"}
        assert missing == []

    def test_missing_required_skill_reduces_score_and_is_reported(self):
        profile_skills = [{"name": "Python"}]
        job_skills = [
            {"name": "Python", "importance": "required"},
            {"name": "Kubernetes", "importance": "required"},
        ]
        score, matched, missing = compute_technical_score(profile_skills, job_skills)
        assert 0 < score < 100
        assert matched == ["Python"]
        assert missing == ["Kubernetes"]

    def test_required_weighs_more_than_nice_to_have(self):
        # profile has only the nice-to-have skill
        job_skills = [
            {"name": "Python", "importance": "required"},
            {"name": "Docker", "importance": "nice_to_have"},
        ]
        score_missing_required, _, missing_required = compute_technical_score(
            [{"name": "Docker"}], job_skills
        )
        score_missing_nice, _, missing_nice = compute_technical_score(
            [{"name": "Python"}], job_skills
        )
        # Missing the required skill should hurt more than missing the nice-to-have one.
        assert score_missing_required < score_missing_nice
        assert missing_required == ["Python"]
        assert missing_nice == []  # nice_to_have misses aren't reported as "missing"

    def test_case_insensitive_and_synonym_matching(self):
        profile_skills = [{"name": "js"}, {"name": "k8s"}]
        job_skills = [
            {"name": "JavaScript", "importance": "required"},
            {"name": "Kubernetes", "importance": "required"},
        ]
        score, matched, missing = compute_technical_score(profile_skills, job_skills)
        assert score == 100.0
        assert set(matched) == {"JavaScript", "Kubernetes"}

    def test_no_required_skills_scores_100(self):
        score, matched, missing = compute_technical_score([{"name": "Python"}], [])
        assert score == 100.0
        assert matched == []
        assert missing == []


# ---------------------------------------------------------------------------
# Experience years extraction / scoring
# ---------------------------------------------------------------------------


class TestExperienceYears:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Looking for 5+ years of experience", 5.0),
            ("3-5 years of Python development", 3.0),
            ("Requires 7 años de experiencia", 7.0),
            ("No explicit requirement here", None),
            ("2+ years with React and 4+ years overall", 2.0),
        ],
    )
    def test_extract_required_years(self, text, expected):
        assert extract_required_years(text) == expected

    def test_relevant_experience_years_sums_matching_entries_only(self):
        experience = [
            {
                "start_date": "2020-01",
                "end_date": "2022-01",
                "skills_used": ["Python", "Django"],
            },
            {
                "start_date": "2015-01",
                "end_date": "2017-01",
                "skills_used": ["PHP"],
            },
        ]
        years = compute_relevant_experience_years(experience, {"Python"})
        assert years == pytest.approx(2.0, abs=0.05)

    def test_null_end_date_treated_as_present(self):
        experience = [{"start_date": "2020-01", "end_date": None, "skills_used": ["Python"]}]
        years = compute_relevant_experience_years(experience, {"Python"})
        assert years > 0

    def test_experience_score_ratio_capped_at_100(self):
        experience = [{"start_date": "2010-01", "end_date": "2024-01", "skills_used": ["Python"]}]
        score, required, relevant = compute_experience_score(
            experience, ["2+ years of Python"], "", {"Python"}
        )
        assert score == 100.0
        assert required == 2.0

    def test_experience_score_graceful_without_explicit_requirement(self):
        experience = [{"start_date": "2020-01", "end_date": "2022-01", "skills_used": ["Python"]}]
        score, required, relevant = compute_experience_score(experience, [], "", {"Python"})
        assert required is None
        assert 0 <= score <= 100

    def test_experience_score_zero_relevant_years_no_requirement(self):
        score, required, relevant = compute_experience_score([], [], "", {"Python"})
        assert required is None
        assert relevant == 0
        assert score == 60.0  # neutral default


# ---------------------------------------------------------------------------
# Semantic score (offline fallback)
# ---------------------------------------------------------------------------


class TestSemanticScore:
    def test_similar_texts_score_higher_than_unrelated(self):
        profile_text = "Backend engineer with experience in Python, FastAPI and PostgreSQL databases."
        job_text_similar = "We are looking for a backend engineer skilled in Python, FastAPI and PostgreSQL."
        job_text_unrelated = "Seeking a professional chef with experience in French cuisine and pastry."

        score_similar = compute_semantic_score(profile_text, job_text_similar)
        score_unrelated = compute_semantic_score(profile_text, job_text_unrelated)

        assert score_similar > score_unrelated

    def test_empty_text_scores_zero(self):
        assert compute_semantic_score("", "something") == 0.0
        assert compute_semantic_score("something", "") == 0.0


# ---------------------------------------------------------------------------
# End-to-end compute_match
# ---------------------------------------------------------------------------


class TestComputeMatch:
    def test_overall_score_is_weighted_average(self):
        profile = make_profile()
        job = make_job()
        result = compute_match(profile, job, use_llm=False)

        expected_overall = round(
            0.5 * result["technical_score"] + 0.3 * result["experience_score"] + 0.2 * result["semantic_score"],
            2,
        )
        assert result["overall_score"] == expected_overall
        assert 0 <= result["overall_score"] <= 100
        assert isinstance(result["matched_skills"], list)
        assert isinstance(result["missing_skills"], list)
        assert isinstance(result["concerns"], list)

    def test_missing_skills_produce_concern(self):
        profile = make_profile(skills=[{"name": "Java"}], experience=[])
        job = make_job()
        result = compute_match(profile, job, use_llm=False)
        assert result["missing_skills"]
        assert any("habilidad" in c.lower() or "años" in c.lower() for c in result["concerns"])

    def test_use_llm_false_never_touches_anthropic(self, monkeypatch):
        import app.services.match_engine as mod

        monkeypatch.setattr(mod, "get_anthropic_client", lambda: object())

        def _boom(*args, **kwargs):
            raise AssertionError("compute_match(use_llm=False) must not call the LLM scorer")

        monkeypatch.setattr(mod, "_try_anthropic_semantic_score", _boom)
        result = compute_match(make_profile(), make_job(), use_llm=False)
        assert 0 <= result["semantic_score"] <= 100

    def test_use_llm_true_prefers_llm_score_when_available(self, monkeypatch):
        import app.services.match_engine as mod

        monkeypatch.setattr(mod, "_try_anthropic_semantic_score", lambda *a, **k: 42.0)
        result = compute_match(make_profile(), make_job(), use_llm=True)
        assert result["semantic_score"] == 42.0

    def test_use_llm_true_falls_back_when_llm_returns_none(self, monkeypatch):
        import app.services.match_engine as mod

        monkeypatch.setattr(mod, "_try_anthropic_semantic_score", lambda *a, **k: None)
        result = compute_match(make_profile(), make_job(), use_llm=True)
        assert 0 <= result["semantic_score"] <= 100


# ---------------------------------------------------------------------------
# LLM-based semantic score (optional, requires ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------


class TestAnthropicSemanticScore:
    def test_returns_none_without_api_key(self, monkeypatch):
        import app.services.match_engine as mod

        monkeypatch.setattr(mod, "get_anthropic_client", lambda: None)
        assert mod._try_anthropic_semantic_score("profile text", "job text") is None

    def test_parses_a_well_formed_numeric_reply(self, monkeypatch):
        import app.services.match_engine as mod

        fake_block = SimpleNamespace(type="text", text="87")
        fake_response = SimpleNamespace(content=[fake_block])

        class FakeMessages:
            def create(self, **kwargs):
                return fake_response

        fake_client = SimpleNamespace(messages=FakeMessages())
        monkeypatch.setattr(mod, "get_anthropic_client", lambda: fake_client)
        score = mod._try_anthropic_semantic_score("backend engineer", "backend role")
        assert score == 87.0

    def test_clamps_out_of_range_reply_to_0_100(self, monkeypatch):
        import app.services.match_engine as mod

        fake_response = SimpleNamespace(content=[SimpleNamespace(type="text", text="140")])

        fake_client = SimpleNamespace(
            messages=SimpleNamespace(create=lambda **kwargs: fake_response)
        )
        monkeypatch.setattr(mod, "get_anthropic_client", lambda: fake_client)
        assert mod._try_anthropic_semantic_score("a", "b") == 100.0

    def test_returns_none_on_unparsable_reply(self, monkeypatch):
        import app.services.match_engine as mod

        fake_response = SimpleNamespace(content=[SimpleNamespace(type="text", text="not a number")])

        fake_client = SimpleNamespace(
            messages=SimpleNamespace(create=lambda **kwargs: fake_response)
        )
        monkeypatch.setattr(mod, "get_anthropic_client", lambda: fake_client)
        assert mod._try_anthropic_semantic_score("a", "b") is None

    def test_returns_none_when_the_call_raises(self, monkeypatch):
        """A network error mid-request must degrade to the offline scorer,
        not surface. Construction now happens in get_anthropic_client, so
        the failure this simulates is the call itself — which is also the
        realistic one: a timeout or a 401 happens on the request, not while
        building the client object."""
        import app.services.match_engine as mod

        def _boom(**kwargs):
            raise RuntimeError("network unreachable")

        fake_client = SimpleNamespace(messages=SimpleNamespace(create=_boom))
        monkeypatch.setattr(mod, "get_anthropic_client", lambda: fake_client)
        assert mod._try_anthropic_semantic_score("a", "b") is None
