"""Aplicar al deslizar, de punta a punta: el swipe prepara, el usuario
responde lo que falta, aprueba, y la aplicacion sale (o se le devuelve).

El formulario de Greenhouse es uno fijo y el agente de envio se sustituye
(submit.call_agent): ningun test sale a Internet ni envia nada real. Sin IA
en la suite (conftest.py), asi que el CV sale del adaptador por reglas.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.application_draft import ApplicationDraft
from app.models.career_profile import CareerProfile
from app.models.enums import ApplicationStatus, JobSource
from app.models.job import Job
from app.models.resume_version import ResumeVersion
from app.models.user import User
from app.services.apply_agent import pipeline
from app.services.apply_agent import submit as submit_mod
from app.services.apply_agent.greenhouse import parse_form

GH_URL = "https://job-boards.greenhouse.io/acme/jobs/123"

BASICO = [
    {"label": "First Name", "required": True, "fields": [{"name": "first_name", "type": "input_text"}]},
    {"label": "Last Name", "required": True, "fields": [{"name": "last_name", "type": "input_text"}]},
    {"label": "Email", "required": True, "fields": [{"name": "email", "type": "input_text"}]},
    {"label": "Resume/CV", "required": True, "fields": [{"name": "resume", "type": "input_file"}]},
]
CON_PREGUNTAS = BASICO + [
    {"label": "Why Acme?", "required": True, "fields": [{"name": "question_2", "type": "textarea"}]},
    {
        "label": "Preferred working hours",
        "required": True,
        "fields": [{"name": "question_3", "type": "multi_value_single_select",
                    "values": [{"label": "Morning", "value": 10}, {"label": "Evening", "value": 11}]}],
    },
]


def _form(preguntas):
    return {
        "title": "Backend Engineer",
        "company_name": "Acme",
        "absolute_url": GH_URL,
        "language": "en",
        "questions": preguntas,
    }


def _fake_form(monkeypatch, preguntas):
    async def fake(board, job_id):
        return parse_form(_form(preguntas), board, job_id)

    monkeypatch.setattr(pipeline, "fetch_greenhouse_form", fake)


async def _job(apply_url=GH_URL, apply_email=None, description="Build APIs in Python.") -> Job:
    async with AsyncSessionLocal() as session:
        job = Job(
            source=JobSource.greenhouse,
            title="Backend Engineer",
            company="Acme",
            description=description,
            requirements=[],
            responsibilities=[],
            skills_required=[{"name": "Python"}],
            source_url=apply_url or "https://example.com/jobs/1",
            apply_url=apply_url,
            apply_email=apply_email,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


async def _profile(user):
    async with AsyncSessionLocal() as session:
        session.add(
            CareerProfile(
                user_id=user.id,
                headline="Backend developer",
                summary="Backend developer building Python APIs.",
                contact_info={"phone": "+1 809 555 0100", "country": "República Dominicana",
                              "linkedin": "https://linkedin.com/in/x"},
                skills=[{"name": "Python"}],
                experience=[{"company": "Now Co", "title": "Dev", "start_date": "2023-01",
                             "bullets": ["Built Python APIs"]}],
                languages=[{"name": "English", "level": "C1"}, {"name": "Spanish", "level": "Native"}],
            )
        )
        await session.commit()


async def _set_mode(user, mode):
    async with AsyncSessionLocal() as session:
        await session.execute(update(User).where(User.id == user.id).values(apply_mode=mode))
        await session.commit()


async def _draft_for(application_id) -> ApplicationDraft:
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(select(ApplicationDraft).where(ApplicationDraft.application_id == application_id))
        ).scalar_one_or_none()


async def _swipe(async_client, headers, job):
    resp = await async_client.post(f"/jobs/{job.id}/decision", headers=headers, json={"decision": "right"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ------------------------------------------------------------------ ajustes

async def test_settings_default_to_review_and_can_change(async_client, user_and_headers):
    _, headers = user_and_headers
    body = (await async_client.get("/apply-agent/settings", headers=headers)).json()
    assert body["apply_mode"] == "review"
    assert body["agent_available"] is False  # conftest apaga el agente

    resp = await async_client.put("/apply-agent/settings", headers=headers, json={"apply_mode": "auto"})
    assert resp.status_code == 200 and resp.json()["apply_mode"] == "auto"
    bad = await async_client.put("/apply-agent/settings", headers=headers, json={"apply_mode": "spam"})
    assert bad.status_code == 422


async def test_save_mode_only_saves(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    await _profile(user)
    await _set_mode(user, "save")
    _fake_form(monkeypatch, BASICO)
    app_id = await _swipe(async_client, headers, await _job())
    assert await _draft_for(app_id) is None


# ------------------------------------------------------------------ modo revisar

async def test_swipe_prepares_and_waits_for_the_missing_answers(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    await _profile(user)
    _fake_form(monkeypatch, CON_PREGUNTAS)
    app_id = await _swipe(async_client, headers, await _job())

    draft = (await async_client.get(f"/applications/{app_id}/draft", headers=headers)).json()
    assert draft["channel"] == "greenhouse"
    assert draft["status"] == "needs_user"
    assert set(draft["content"]["pending_required"]) == {"question_2", "question_3"}
    campos = {f["key"]: f for f in draft["content"]["fields"]}
    assert campos["resume"]["display"] == "Tu CV para esta vacante (PDF)"
    assert draft["content"]["grounding"]["ok"] is True
    # La postulacion queda guardada, no "aplicada": nada ha salido.
    async with AsyncSessionLocal() as session:
        app_row = (await session.execute(select(Application).where(Application.id == app_id))).scalar_one()
        assert app_row.status == ApplicationStatus.saved
        assert app_row.resume_version_id is not None
        cvs = (await session.execute(select(ResumeVersion))).scalars().all()
        assert len(cvs) == 1

    # Respuestas invalidas se rechazan enteras.
    malo = await async_client.patch(f"/applications/{app_id}/draft/answers", headers=headers,
                                    json={"answers": {"question_3": 99}})
    assert malo.status_code == 422
    archivo = await async_client.patch(f"/applications/{app_id}/draft/answers", headers=headers,
                                      json={"answers": {"resume": "x"}})
    assert archivo.status_code == 422

    # No se puede enviar con obligatorias pendientes.
    pronto = await async_client.post(f"/applications/{app_id}/draft/submit", headers=headers)
    assert pronto.status_code == 409

    ok = await async_client.patch(
        f"/applications/{app_id}/draft/answers",
        headers=headers,
        json={"answers": {"question_2": "I build Python APIs.", "question_3": 10}},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["status"] == "ready"
    campos = {f["key"]: f for f in body["content"]["fields"]}
    assert campos["question_3"]["display"] == "Morning"
    assert campos["question_2"]["source"] == "user"

    # Lista en la bandeja.
    bandeja = (await async_client.get("/apply-agent/drafts", headers=headers)).json()
    assert [d["status"] for d in bandeja] == ["ready"]
    assert bandeja[0]["job"]["company"] == "Acme"


async def test_approving_sends_through_the_agent_and_marks_applied(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    await _profile(user)
    _fake_form(monkeypatch, BASICO)
    monkeypatch.setattr(settings, "APPLY_AGENT_URL", "http://agent.test")
    enviados = []

    async def fake_agent(payload):
        enviados.append(payload)
        return {"outcome": "submitted", "filled": ["first_name"], "screenshot_b64": "xx"}

    monkeypatch.setattr(submit_mod, "call_agent", fake_agent)
    app_id = await _swipe(async_client, headers, await _job())
    assert (await _draft_for(app_id)).status == "ready"

    resp = await async_client.post(f"/applications/{app_id}/draft/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "submitted" and body["submitted_at"]
    assert "screenshot_b64" not in body["content"]["submission"]

    [payload] = enviados
    assert payload["draft"]["form_url"].startswith("https://")
    assert payload["resume_pdf"].startswith("JVBER")  # base64 de "%PDF"
    valores = {f["key"]: f.get("value") for f in payload["draft"]["fields"]}
    assert valores["first_name"] == "Router" and valores["email"] == "router-test@example.com"

    async with AsyncSessionLocal() as session:
        app_row = (await session.execute(select(Application).where(Application.id == app_id))).scalar_one()
        assert app_row.status == ApplicationStatus.applied
        assert app_row.applied_at is not None
        assert "Greenhouse" in (app_row.notes or "")

    # Dos veces no sale.
    otra = await async_client.post(f"/applications/{app_id}/draft/submit", headers=headers)
    assert otra.status_code == 200 and len(enviados) == 1


async def test_a_captcha_hands_it_back_and_the_user_marks_it_sent(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    await _profile(user)
    _fake_form(monkeypatch, BASICO)
    monkeypatch.setattr(settings, "APPLY_AGENT_URL", "http://agent.test")

    async def challenge(payload):
        return {"outcome": "challenge"}

    monkeypatch.setattr(submit_mod, "call_agent", challenge)
    app_id = await _swipe(async_client, headers, await _job())
    body = (await async_client.post(f"/applications/{app_id}/draft/submit", headers=headers)).json()
    assert body["status"] == "handoff"
    assert "CAPTCHA" in body["content"]["handoff_reason"]
    async with AsyncSessionLocal() as session:
        app_row = (await session.execute(select(Application).where(Application.id == app_id))).scalar_one()
        assert app_row.status == ApplicationStatus.saved  # nada se dio por enviado

    hecho = (await async_client.post(f"/applications/{app_id}/draft/mark-sent", headers=headers)).json()
    assert hecho["status"] == "submitted"
    async with AsyncSessionLocal() as session:
        app_row = (await session.execute(select(Application).where(Application.id == app_id))).scalar_one()
        assert app_row.status == ApplicationStatus.applied


async def test_without_an_agent_it_is_handed_off(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    await _profile(user)
    _fake_form(monkeypatch, BASICO)
    app_id = await _swipe(async_client, headers, await _job())
    body = (await async_client.post(f"/applications/{app_id}/draft/submit", headers=headers)).json()
    assert body["status"] == "handoff"
    assert "extensión" in body["content"]["handoff_reason"]


async def test_other_sites_are_ready_to_send_by_hand(async_client, user_and_headers):
    user, headers = user_and_headers
    await _profile(user)
    app_id = await _swipe(async_client, headers, await _job(apply_url="https://acme.wd1.myworkdayjobs.com/x"))
    draft = await _draft_for(app_id)
    assert draft.channel == "external" and draft.status == "handoff"
    assert draft.resume_version_id is not None


async def test_without_a_profile_it_says_so(async_client, user_and_headers, monkeypatch):
    _, headers = user_and_headers
    _fake_form(monkeypatch, BASICO)
    app_id = await _swipe(async_client, headers, await _job())
    draft = await _draft_for(app_id)
    assert draft.status == "failed"
    assert "Sube tu CV" in draft.error


# ------------------------------------------------------------------ modo automatico

async def test_auto_mode_schedules_with_undo_and_the_clock_sends_it(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    await _profile(user)
    await _set_mode(user, "auto")
    _fake_form(monkeypatch, BASICO)
    monkeypatch.setattr(settings, "APPLY_AGENT_URL", "http://agent.test")
    enviados = []

    async def fake_agent(payload):
        enviados.append(payload)
        return {"outcome": "submitted"}

    monkeypatch.setattr(submit_mod, "call_agent", fake_agent)
    app_id = await _swipe(async_client, headers, await _job())
    draft = await _draft_for(app_id)
    assert draft.status == "scheduled", draft.content.get("review_reasons")
    assert draft.scheduled_for > datetime.now(timezone.utc) + timedelta(minutes=settings.APPLY_UNDO_MINUTES - 1)

    # Antes de su hora no sale.
    async with AsyncSessionLocal() as session:
        await submit_mod.run_due(session)
    assert enviados == []

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(ApplicationDraft).where(ApplicationDraft.id == draft.id)
            .values(scheduled_for=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await session.commit()
    async with AsyncSessionLocal() as session:
        assert await submit_mod.run_due(session) == 1
    assert len(enviados) == 1
    assert (await _draft_for(app_id)).status == "submitted"
    ajustes = (await async_client.get("/apply-agent/settings", headers=headers)).json()
    assert ajustes["auto_sent_today"] == 1


async def test_auto_mode_can_be_undone(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    await _profile(user)
    await _set_mode(user, "auto")
    _fake_form(monkeypatch, BASICO)
    app_id = await _swipe(async_client, headers, await _job())
    assert (await _draft_for(app_id)).status == "scheduled"

    resp = await async_client.post(f"/applications/{app_id}/draft/cancel", headers=headers)
    assert resp.status_code == 200 and resp.json()["status"] == "cancelled"
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(ApplicationDraft).where(ApplicationDraft.application_id == app_id)
            .values(scheduled_for=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await session.commit()
        assert await submit_mod.run_due(session) == 0


async def test_auto_mode_waits_when_something_needs_review(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    await _profile(user)
    await _set_mode(user, "auto")
    _fake_form(monkeypatch, BASICO)
    # Exige alemán: el perfil no lo tiene.
    app_id = await _swipe(async_client, headers, await _job(description="Fluent German required. Build APIs."))
    draft = await _draft_for(app_id)
    assert draft.status == "ready"
    assert "gate" in draft.content["review_reasons"]
    assert draft.content["gates"][0]["code"] == "language"


async def test_auto_mode_respects_the_daily_limit(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    await _profile(user)
    await _set_mode(user, "auto")
    _fake_form(monkeypatch, BASICO)
    monkeypatch.setattr(settings, "APPLY_DAILY_AUTO_LIMIT", 0)
    app_id = await _swipe(async_client, headers, await _job())
    draft = await _draft_for(app_id)
    assert draft.status == "ready"
    assert draft.content["auto_limit_reached"] is True


async def test_cannot_touch_someone_elses_draft(async_client, user_and_headers, monkeypatch):
    from app.core.security import create_access_token, hash_password

    user, headers = user_and_headers
    await _profile(user)
    _fake_form(monkeypatch, BASICO)
    app_id = await _swipe(async_client, headers, await _job())
    async with AsyncSessionLocal() as session:
        otro = User(email="otro@example.com", hashed_password=hash_password("Test1234!"),
                    full_name="Otro", email_verified=True)
        session.add(otro)
        await session.commit()
        await session.refresh(otro)
    ajenos = {"Authorization": f"Bearer {create_access_token(str(otro.id))}"}
    for metodo, ruta in (("post", "submit"), ("post", "cancel"), ("post", "mark-sent")):
        resp = await getattr(async_client, metodo)(f"/applications/{app_id}/draft/{ruta}", headers=ajenos)
        assert resp.status_code == 404
    assert (await async_client.get("/apply-agent/drafts", headers=ajenos)).json() == []
