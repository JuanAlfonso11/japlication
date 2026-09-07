"""Integration coverage for the endpoints added after the first audit.

Until this file existed those features were tested only at the pure-function
level (aggregate_skill_gaps, build_interview_prep, the resume adapter), which
proves the logic and nothing about the HTTP surface: not authentication, not
ownership, not whether a field the client sends actually survives the round
trip. That gap already produced one real bug — `screening_answers` was added
to the write schema but not the read one, so answers saved fine and
`GET /profile` never returned them. It was caught by reading openapi.json,
which is luck, not process. Everything below is the process.
"""

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models.career_profile import CareerProfile
from app.models.enums import ApplicationStatus, GenerationSource, JobSource
from app.models.application import Application
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.resume_version import ResumeVersion
from app.models.user import User


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


async def _make_job(title: str = "Backend Engineer", company: str = "Acme", requirements=None) -> Job:
    async with AsyncSessionLocal() as session:
        job = Job(
            source=JobSource.manual,
            title=title,
            company=company,
            description="Construimos sistemas distribuidos para pagos.",
            requirements=requirements if requirements is not None else ["5+ años en Python"],
            responsibilities=[],
            skills_required=[{"name": "Python", "importance": "required"}],
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


async def _make_profile(user_id, *, experience=None) -> CareerProfile:
    async with AsyncSessionLocal() as session:
        profile = CareerProfile(
            user_id=user_id,
            headline="Backend Engineer",
            summary="Diez años construyendo APIs.",
            skills=[{"name": "Python", "category": "backend", "level": "expert"}],
            experience=experience
            if experience is not None
            else [
                {
                    "company": "Acme",
                    "title": "Backend Engineer",
                    "bullets": ["Migré el pipeline a Kubernetes reduciendo el costo 30%"],
                }
            ],
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


async def _make_match(user_id, job_id, *, missing=None, matched=None) -> JobMatch:
    async with AsyncSessionLocal() as session:
        match = JobMatch(
            user_id=user_id,
            job_id=job_id,
            overall_score=70,
            technical_score=70,
            experience_score=70,
            semantic_score=70,
            matched_skills=matched if matched is not None else ["Python"],
            missing_skills=missing if missing is not None else ["Kubernetes"],
            concerns=[],
        )
        session.add(match)
        await session.commit()
        await session.refresh(match)
        return match


async def _make_application(user_id, job_id, status: ApplicationStatus) -> Application:
    async with AsyncSessionLocal() as session:
        app_row = Application(user_id=user_id, job_id=job_id, status=status)
        session.add(app_row)
        await session.commit()
        await session.refresh(app_row)
        return app_row


async def _make_other_user() -> tuple[User, dict]:
    """A second, unrelated account — the only way to prove a route filters by
    owner rather than just happening to return the right rows."""
    async with AsyncSessionLocal() as session:
        user = User(
            email="intruder@example.com",
            hashed_password=hash_password("Test1234!"),
            full_name="Intruder",
            email_verified=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


# --------------------------------------------------------------------------
# GET /match/skill-gaps
# --------------------------------------------------------------------------


async def test_skill_gaps_requires_authentication(async_client):
    assert (await async_client.get("/match/skill-gaps")).status_code == 401


async def test_skill_gaps_aggregates_over_jobs_the_user_wanted(async_client, user_and_headers):
    user, headers = user_and_headers
    await _make_profile(user.id)

    # Four saved jobs, three of which are missing Kubernetes.
    for i in range(4):
        job = await _make_job(title=f"Job {i}")
        await _make_match(user.id, job.id, missing=["Kubernetes"] if i < 3 else ["Rust"])
        await _make_application(user.id, job.id, ApplicationStatus.saved)

    resp = await async_client.get("/match/skill-gaps", headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["jobs_considered"] == 4
    assert body["based_on_all_matches"] is False
    top = body["gaps"][0]
    assert top["skill"] == "Kubernetes"
    assert top["job_count"] == 3
    assert top["percentage"] == 75
    assert "Kubernetes" in body["summary"]


async def test_skill_gaps_ignores_jobs_the_user_passed_on(async_client, user_and_headers):
    """A skill missing from postings you swiped away is noise, not a gap."""
    user, headers = user_and_headers
    await _make_profile(user.id)

    for i in range(4):
        job = await _make_job(title=f"Saved {i}")
        await _make_match(user.id, job.id, missing=["Kubernetes"])
        await _make_application(user.id, job.id, ApplicationStatus.saved)

    for i in range(6):
        job = await _make_job(title=f"Passed {i}")
        await _make_match(user.id, job.id, missing=["COBOL"])
        await _make_application(user.id, job.id, ApplicationStatus.passed)

    body = (await async_client.get("/match/skill-gaps", headers=headers)).json()

    assert body["jobs_considered"] == 4
    assert [g["skill"] for g in body["gaps"]] == ["Kubernetes"]


async def test_skill_gaps_falls_back_and_says_so_with_too_few_decisions(
    async_client, user_and_headers
):
    """One saved job would otherwise produce "100% of what you saved"."""
    user, headers = user_and_headers
    await _make_profile(user.id)

    for i in range(3):
        job = await _make_job(title=f"Scored {i}")
        await _make_match(user.id, job.id, missing=["Kubernetes"])

    job = await _make_job(title="The only saved one")
    await _make_match(user.id, job.id, missing=["Kubernetes"])
    await _make_application(user.id, job.id, ApplicationStatus.saved)

    body = (await async_client.get("/match/skill-gaps", headers=headers)).json()

    assert body["based_on_all_matches"] is True
    # The honest-phrasing contract: no confident summary in fallback mode.
    assert body["summary"] is None


async def test_skill_gaps_never_leaks_another_users_matches(async_client, user_and_headers):
    user, headers = user_and_headers
    await _make_profile(user.id)
    other, _ = await _make_other_user()

    for i in range(5):
        job = await _make_job(title=f"Other user's job {i}")
        await _make_match(other.id, job.id, missing=["Kubernetes"])
        await _make_application(other.id, job.id, ApplicationStatus.saved)

    body = (await async_client.get("/match/skill-gaps", headers=headers)).json()

    assert body["jobs_considered"] == 0
    assert body["gaps"] == []


async def test_skill_gaps_is_empty_for_a_brand_new_account(async_client, user_and_headers):
    _, headers = user_and_headers
    resp = await async_client.get("/match/skill-gaps", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["gaps"] == []


# --------------------------------------------------------------------------
# POST /jobs/{job_id}/interview-prep
# --------------------------------------------------------------------------


async def test_interview_prep_requires_authentication(async_client):
    job = await _make_job()
    assert (await async_client.post(f"/jobs/{job.id}/interview-prep")).status_code == 401


async def test_interview_prep_is_grounded_in_the_users_own_bullets(async_client, user_and_headers):
    user, headers = user_and_headers
    await _make_profile(user.id)
    job = await _make_job()
    await _make_match(user.id, job.id, matched=["Kubernetes"], missing=[])

    resp = await async_client.post(f"/jobs/{job.id}/interview-prep", headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["questions"]
    assert body["generated_by"] in ("ai", "manual")

    points = " ".join(p for q in body["questions"] for p in q["talking_points"])
    # The bullet from the profile must be what backs the answer.
    assert "pipeline" in points.lower()


async def test_interview_prep_frames_a_missing_skill_as_a_gap_not_an_answer(
    async_client, user_and_headers
):
    """The rule the whole product rests on: never invent experience."""
    user, headers = user_and_headers
    await _make_profile(user.id)
    job = await _make_job()
    await _make_match(user.id, job.id, matched=[], missing=["Rust"])

    body = (await async_client.post(f"/jobs/{job.id}/interview-prep", headers=headers)).json()

    gaps = [q for q in body["questions"] if q["category"] == "brecha"]
    assert gaps, "una skill faltante debe producir una pregunta de brecha"
    assert "Rust" in gaps[0]["question"]
    assert "no inventes" in " ".join(gaps[0]["talking_points"]).lower()


async def test_interview_prep_404s_for_a_job_that_does_not_exist(async_client, user_and_headers):
    user, headers = user_and_headers
    await _make_profile(user.id)
    missing_id = "00000000-0000-0000-0000-000000000000"
    resp = await async_client.post(f"/jobs/{missing_id}/interview-prep", headers=headers)
    assert resp.status_code == 404


async def test_interview_prep_asks_for_a_profile_before_it_can_help(async_client, user_and_headers):
    _, headers = user_and_headers
    job = await _make_job()
    resp = await async_client.post(f"/jobs/{job.id}/interview-prep", headers=headers)
    assert resp.status_code == 400


# --------------------------------------------------------------------------
# PATCH /resume-versions/{id}
# --------------------------------------------------------------------------


async def _make_resume(user_id, profile_id, job_id) -> ResumeVersion:
    async with AsyncSessionLocal() as session:
        resume = ResumeVersion(
            user_id=user_id,
            career_profile_id=profile_id,
            job_id=job_id,
            title="Backend Engineer @ Acme",
            content={
                "summary": "Resumen generado.",
                "skills": ["Python"],
                "experience": [
                    {"company": "Acme", "title": "Backend Engineer", "bullets": ["Viñeta original"]}
                ],
                "education": [],
            },
            change_log=[],
            generated_by=GenerationSource.ai,
        )
        session.add(resume)
        await session.commit()
        await session.refresh(resume)
        return resume


async def test_editing_a_resume_saves_the_text_and_stamps_it_as_edited(
    async_client, user_and_headers
):
    user, headers = user_and_headers
    profile = await _make_profile(user.id)
    job = await _make_job()
    resume = await _make_resume(user.id, profile.id, job.id)

    assert resume.edited_at is None

    resp = await async_client.patch(
        f"/resume-versions/{resume.id}",
        headers=headers,
        json={
            "content": {
                "summary": "Mi propia redacción.",
                "skills": ["Python", "Kubernetes"],
                "experience_bullets": {"0": ["Viñeta corregida por mí"]},
            }
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["content"]["summary"] == "Mi propia redacción."
    assert body["content"]["skills"] == ["Python", "Kubernetes"]
    assert body["content"]["experience"][0]["bullets"] == ["Viñeta corregida por mí"]
    # The stamp is what later makes this version the preferred one to reuse.
    assert body["edited_at"] is not None


async def test_editing_leaves_untouched_fields_alone(async_client, user_and_headers):
    """A partial PATCH must not blank out what it didn't mention."""
    user, headers = user_and_headers
    profile = await _make_profile(user.id)
    job = await _make_job()
    resume = await _make_resume(user.id, profile.id, job.id)

    resp = await async_client.patch(
        f"/resume-versions/{resume.id}",
        headers=headers,
        json={"content": {"summary": "Solo cambio el resumen."}},
    )

    body = resp.json()
    assert body["content"]["summary"] == "Solo cambio el resumen."
    assert body["content"]["skills"] == ["Python"]
    assert body["content"]["experience"][0]["bullets"] == ["Viñeta original"]


async def test_cannot_edit_someone_elses_resume(async_client, user_and_headers):
    """The ownership check, stated as a test rather than assumed."""
    user, _ = user_and_headers
    profile = await _make_profile(user.id)
    job = await _make_job()
    resume = await _make_resume(user.id, profile.id, job.id)

    _, intruder_headers = await _make_other_user()

    resp = await async_client.patch(
        f"/resume-versions/{resume.id}",
        headers=intruder_headers,
        json={"content": {"summary": "Secuestrado."}},
    )
    assert resp.status_code == 404

    # And the original text is untouched.
    async with AsyncSessionLocal() as session:
        fresh = (
            await session.execute(select(ResumeVersion).where(ResumeVersion.id == resume.id))
        ).scalar_one()
        assert fresh.content["summary"] == "Resumen generado."


async def test_cannot_read_someone_elses_resume(async_client, user_and_headers):
    """Found by mutation-testing this very file: deleting the ownership
    filter from BOTH resume routes only made the PATCH test fail, so the
    GET's filter was load-bearing and unproven. A tailored CV carries the
    user's full work history — it is not a public document."""
    user, _ = user_and_headers
    profile = await _make_profile(user.id)
    job = await _make_job()
    resume = await _make_resume(user.id, profile.id, job.id)

    _, intruder_headers = await _make_other_user()

    resp = await async_client.get(f"/resume-versions/{resume.id}", headers=intruder_headers)
    assert resp.status_code == 404


async def test_cannot_list_someone_elses_resumes(async_client, user_and_headers):
    user, _ = user_and_headers
    profile = await _make_profile(user.id)
    job = await _make_job()
    await _make_resume(user.id, profile.id, job.id)

    _, intruder_headers = await _make_other_user()

    resp = await async_client.get("/resume-versions", headers=intruder_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_editing_a_resume_requires_authentication(async_client, user_and_headers):
    user, _ = user_and_headers
    profile = await _make_profile(user.id)
    job = await _make_job()
    resume = await _make_resume(user.id, profile.id, job.id)

    resp = await async_client.patch(
        f"/resume-versions/{resume.id}", json={"content": {"summary": "x"}}
    )
    assert resp.status_code == 401


async def test_editing_rejects_a_bullet_index_that_does_not_exist(async_client, user_and_headers):
    user, headers = user_and_headers
    profile = await _make_profile(user.id)
    job = await _make_job()
    resume = await _make_resume(user.id, profile.id, job.id)

    resp = await async_client.patch(
        f"/resume-versions/{resume.id}",
        headers=headers,
        json={"content": {"experience_bullets": {"99": ["fuera de rango"]}}},
    )
    assert resp.status_code == 400


# --------------------------------------------------------------------------
# screening_answers round trip — regression test for a bug that shipped
# --------------------------------------------------------------------------


async def test_screening_answers_survive_the_round_trip(async_client, user_and_headers):
    """The exact bug this file's docstring describes: the field was in the
    write schema but not the read one, so answers saved and then vanished."""
    _, headers = user_and_headers

    answers = [
        {"question": "¿Expectativa salarial?", "answer": "USD 90k"},
        {"question": "¿Autorización para trabajar?", "answer": "Sí, ciudadanía UE"},
    ]

    put = await async_client.put(
        "/profile",
        headers=headers,
        json={
            "headline": "Backend Engineer",
            "summary": "",
            "contact_info": {},
            "skills": [],
            "experience": [],
            "education": [],
            "certifications": [],
            "languages": [],
            "screening_answers": answers,
        },
    )
    assert put.status_code == 200
    assert put.json()["screening_answers"] == answers

    # The half that was broken: reading them back.
    got = await async_client.get("/profile", headers=headers)
    assert got.status_code == 200
    assert got.json()["screening_answers"] == answers


async def test_a_users_screening_answers_are_private_to_them(async_client, user_and_headers):
    _, headers = user_and_headers
    await async_client.put(
        "/profile",
        headers=headers,
        json={
            "headline": "",
            "summary": "",
            "contact_info": {},
            "skills": [],
            "experience": [],
            "education": [],
            "certifications": [],
            "languages": [],
            "screening_answers": [{"question": "Salario", "answer": "confidencial"}],
        },
    )

    _, intruder_headers = await _make_other_user()
    resp = await async_client.get("/profile", headers=intruder_headers)
    # No profile of their own — and certainly not somebody else's.
    assert resp.status_code == 404
