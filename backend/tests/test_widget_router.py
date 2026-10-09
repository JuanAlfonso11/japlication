"""El widget "Próxima vacante" decide sin abrir la app: su credencial propia
solo abre /widget/*, el swipe que hace es el mismo que el de Home, y se
revoca al cerrar sesión, al cambiar de cuenta en el teléfono o al
restablecer la contraseña."""

from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.api.v1.routers import auth
from app.api.v1.routers.widget import describe_place
from app.core.rate_limit import limiter
from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.enums import ApplicationStatus, JobSource
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.widget_token import WidgetToken

DEVICE = "6f1c2b9e-0a4d-4c55-9a1e-3f2b7c8d9e01"


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    monkeypatch.setattr(limiter, "enabled", False)


async def _queue_job(user_id, title: str, score: float) -> Job:
    async with AsyncSessionLocal() as session:
        job = Job(
            source=JobSource.manual,
            title=title,
            company="Acme",
            location="Santiago",
            remote_type="hybrid",
            description="Build things.",
            requirements=[],
            responsibilities=[],
            skills_required=[],
        )
        session.add(job)
        await session.flush()
        session.add(
            JobMatch(
                user_id=user_id,
                job_id=job.id,
                overall_score=score,
                technical_score=score,
                experience_score=score,
                semantic_score=score,
                matched_skills=[],
                missing_skills=[],
                concerns=[],
            )
        )
        await session.commit()
        await session.refresh(job)
        return job


async def _widget_headers(async_client, headers, device=DEVICE) -> dict:
    resp = await async_client.post("/widget/token", headers=headers, json={"device_id": device})
    assert resp.status_code == 201, resp.text
    return {"X-Widget-Token": resp.json()["token"]}


async def test_summary_has_the_widget_payload_shape(async_client, user_and_headers):
    user, headers = user_and_headers
    first = await _queue_job(user.id, "Backend Engineer", 91.4)
    await _queue_job(user.id, "ML Engineer", 75)
    w = await _widget_headers(async_client, headers)

    resp = await async_client.get("/widget/summary", headers=w)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["v"] == 1
    assert body["queueCount"] == 2
    assert body["next"] == {
        "id": str(first.id),
        "title": "Backend Engineer",
        "company": "Acme",
        "place": "Híbrido · Santiago",
        "score": 91,
    }
    assert [j["title"] for j in body["upcoming"]] == ["ML Engineer"]
    assert body["pipeline"] == {"applied": 0, "interviewing": 0, "offer": 0}


async def test_decision_is_the_same_swipe_as_home_and_undo_brings_it_back(async_client, user_and_headers):
    user, headers = user_and_headers
    first = await _queue_job(user.id, "First", 90)
    second = await _queue_job(user.id, "Second", 80)
    w = await _widget_headers(async_client, headers)

    passed = await async_client.post(
        "/widget/decision", headers=w, json={"job_id": str(first.id), "decision": "left"}
    )
    assert passed.status_code == 200, passed.text
    assert passed.json()["summary"]["next"]["id"] == str(second.id)
    application_id = passed.json()["application_id"]

    undone = await async_client.post("/widget/undo", headers=w, json={"application_id": application_id})
    assert undone.status_code == 200, undone.text
    assert undone.json()["summary"]["next"]["id"] == str(first.id)

    saved = await async_client.post(
        "/widget/decision", headers=w, json={"job_id": str(first.id), "decision": "right"}
    )
    assert saved.status_code == 200
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(select(Application).where(Application.job_id == first.id))
        ).scalar_one()
        # Igual que Home: la derecha guarda, no "postula".
        assert row.status == ApplicationStatus.saved
    assert saved.json()["summary"]["queueCount"] == 1


async def test_widget_token_opens_nothing_but_the_widget(async_client, user_and_headers):
    _, headers = user_and_headers
    w = await _widget_headers(async_client, headers)
    as_bearer = {"Authorization": f"Bearer {w['X-Widget-Token']}"}
    assert (await async_client.get("/auth/me", headers=as_bearer)).status_code == 401
    assert (await async_client.get("/profile", headers=as_bearer)).status_code == 401
    assert (await async_client.get("/widget/summary")).status_code == 401
    assert (await async_client.get("/widget/summary", headers={"X-Widget-Token": "nope"})).status_code == 401


async def test_revoke_and_reissue_for_the_same_phone(async_client, user_and_headers):
    _, headers = user_and_headers
    old = await _widget_headers(async_client, headers)
    new = await _widget_headers(async_client, headers)
    # Un teléfono, una credencial: la anterior deja de valer.
    assert (await async_client.get("/widget/summary", headers=old)).status_code == 401
    assert (await async_client.get("/widget/summary", headers=new)).status_code == 200

    assert (await async_client.delete("/widget/token", headers=new)).status_code == 204
    assert (await async_client.get("/widget/summary", headers=new)).status_code == 401


async def test_token_is_stored_hashed_and_device_id_is_validated(async_client, user_and_headers):
    _, headers = user_and_headers
    w = await _widget_headers(async_client, headers)
    async with AsyncSessionLocal() as session:
        stored = (await session.execute(select(WidgetToken))).scalars().all()
    assert len(stored) == 1
    assert stored[0].token_hash != w["X-Widget-Token"]
    assert stored[0].device_id == DEVICE

    bad = await async_client.post("/widget/token", headers=headers, json={"device_id": "../x"})
    assert bad.status_code == 422
    assert (await async_client.post("/widget/token", json={"device_id": DEVICE})).status_code == 401


async def test_password_reset_disconnects_the_widget(async_client, user_and_headers, monkeypatch):
    user, headers = user_and_headers
    mails = []
    monkeypatch.setattr(
        auth.email, "send_password_reset_email", lambda to, name, url, minutes: mails.append(url)
    )
    w = await _widget_headers(async_client, headers)

    await async_client.post("/auth/forgot-password", json={"email": user.email})
    token = parse_qs(urlparse(mails[0]).query)["token"][0]
    resp = await async_client.post("/auth/reset-password", json={"token": token, "password": "Nueva1234!"})
    assert resp.status_code == 200, resp.text

    assert (await async_client.get("/widget/summary", headers=w)).status_code == 401


def test_describe_place_matches_the_frontend():
    assert describe_place("Santiago", "hybrid") == "Híbrido · Santiago"
    assert describe_place("Remote - Worldwide", "remote") == "Remoto"
    assert describe_place("Canada", "remote") == "Remoto · Canada"
    assert describe_place("Madrid", None) == "Madrid"
