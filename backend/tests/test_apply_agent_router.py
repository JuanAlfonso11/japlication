"""Endpoints del agente: preparar, leer y comprobar el perfil.

El formulario se sustituye por uno fijo: los tests nunca piden nada a
Greenhouse, y el LLM no esta configurado en la suite (ver conftest.py), asi
que lo que no resuelve el perfil queda para el usuario.
"""

from sqlalchemy import select

from app.api.v1.routers import apply_agent as router_mod
from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.application_draft import ApplicationDraft
from app.models.career_profile import CareerProfile
from app.models.enums import ApplicationStatus, JobSource
from app.models.job import Job
from app.models.user import User
from app.services.apply_agent.greenhouse import FormUnavailable, parse_form

FORM = {
    "title": "Backend Engineer",
    "company_name": "Acme",
    "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/123",
    "language": "en",
    "questions": [
        {"label": "First Name", "required": True, "fields": [{"name": "first_name", "type": "input_text"}]},
        {"label": "Last Name", "required": True, "fields": [{"name": "last_name", "type": "input_text"}]},
        {"label": "Email", "required": True, "fields": [{"name": "email", "type": "input_text"}]},
        {"label": "Resume/CV", "required": True, "fields": [{"name": "resume", "type": "input_file"}]},
        {
            "label": "Do you require visa sponsorship?",
            "required": True,
            "fields": [{"name": "question_1", "type": "multi_value_single_select",
                        "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}]}],
        },
        {"label": "Why Acme?", "required": True, "fields": [{"name": "question_2", "type": "textarea"}]},
    ],
}


async def _setup(user, apply_url="https://job-boards.greenhouse.io/acme/jobs/123", with_profile=True):
    async with AsyncSessionLocal() as session:
        job = Job(
            source=JobSource.greenhouse,
            title="Backend Engineer",
            company="Acme",
            description="Build APIs.",
            requirements=[],
            responsibilities=[],
            skills_required=[],
            source_url=apply_url,
            apply_url=apply_url,
        )
        session.add(job)
        await session.flush()
        application = Application(user_id=user.id, job_id=job.id, status=ApplicationStatus.saved)
        session.add(application)
        if with_profile:
            session.add(
                CareerProfile(
                    user_id=user.id,
                    contact_info={"phone": "+1 809 555 0100", "country": "República Dominicana",
                                  "linkedin": "https://linkedin.com/in/x"},
                    experience=[{"company": "Now Co", "title": "Dev"}],
                    screening_answers=[{"question": "¿Requieres patrocinio de visa?", "answer": "No"}],
                )
            )
        await session.commit()
        return application.id


def _fake_form(monkeypatch, data=FORM):
    async def fake(board, job_id):
        assert (board, job_id) == ("acme", "123")
        return parse_form(data, board, job_id)

    monkeypatch.setattr(router_mod, "fetch_greenhouse_form", fake)


async def test_prepare_and_read_draft(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    app_id = await _setup(user)
    _fake_form(monkeypatch)

    assert (await async_client.get(f"/applications/{app_id}/draft", headers=headers)).status_code == 404

    resp = await async_client.post(f"/applications/{app_id}/draft", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ats"] == "greenhouse"
    assert body["form_url"] == "https://job-boards.greenhouse.io/acme/jobs/123"
    # "Why Acme?" es obligatoria y sin IA en la suite nadie la contesta.
    assert body["status"] == "needs_user"
    assert body["auto_eligible"] is False
    campos = {f["key"]: f for f in body["content"]["fields"]}
    assert campos["first_name"]["display"] == "Router"
    assert campos["question_1"]["display"] == "No"
    assert "needs_user" in body["content"]["review_reasons"]

    # Rehacerlo reemplaza, no duplica.
    assert (await async_client.post(f"/applications/{app_id}/draft", headers=headers)).status_code == 200
    async with AsyncSessionLocal() as session:
        filas = (await session.execute(select(ApplicationDraft))).scalars().all()
    assert len(filas) == 1

    leido = await async_client.get(f"/applications/{app_id}/draft", headers=headers)
    assert leido.status_code == 200 and leido.json()["id"] == body["id"]


async def test_only_greenhouse_for_now(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    app_id = await _setup(user, apply_url="https://jobs.lever.co/acme/abc")
    _fake_form(monkeypatch)
    resp = await async_client.post(f"/applications/{app_id}/draft", headers=headers)
    assert resp.status_code == 422


async def test_needs_a_profile(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    app_id = await _setup(user, with_profile=False)
    _fake_form(monkeypatch)
    resp = await async_client.post(f"/applications/{app_id}/draft", headers=headers)
    assert resp.status_code == 409


async def test_form_unavailable_is_a_502(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    app_id = await _setup(user)

    async def gone(board, job_id):
        raise FormUnavailable("La oferta ya no existe en Greenhouse.")

    monkeypatch.setattr(router_mod, "fetch_greenhouse_form", gone)
    resp = await async_client.post(f"/applications/{app_id}/draft", headers=headers)
    assert resp.status_code == 502
    assert resp.json()["detail"] == "La oferta ya no existe en Greenhouse."


async def test_cannot_touch_someone_elses_application(async_client, user_and_headers, monkeypatch):
    user, _ = user_and_headers
    app_id = await _setup(user)
    _fake_form(monkeypatch)
    async with AsyncSessionLocal() as session:
        otro = User(email="otro@example.com", hashed_password=hash_password("Test1234!"),
                    full_name="Otro", email_verified=True)
        session.add(otro)
        await session.commit()
        await session.refresh(otro)
    ajenos = {"Authorization": f"Bearer {create_access_token(str(otro.id))}"}

    assert (await async_client.post(f"/applications/{app_id}/draft", headers=ajenos)).status_code == 404
    assert (await async_client.get(f"/applications/{app_id}/draft", headers=ajenos)).status_code == 404


async def test_readiness(async_client, user_and_headers):
    user, headers = user_and_headers
    sin_perfil = (await async_client.get("/apply-agent/readiness", headers=headers)).json()
    assert sin_perfil == {"ready": False, "missing": ["perfil (sube tu CV)"]}

    await _setup(user)
    con_perfil = (await async_client.get("/apply-agent/readiness", headers=headers)).json()
    assert con_perfil["ready"] is False
    # Tiene telefono, LinkedIn, pais y la respuesta de patrocinio; le falta la
    # de autorizacion de trabajo.
    assert con_perfil["missing"] == ["respuesta guardada sobre autorización de trabajo"]
