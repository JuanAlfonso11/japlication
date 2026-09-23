"""Forgot / reset password: no account enumeration, single-use links, and
every old session dies with the old password."""

from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.api.v1.routers import auth
from app.core.rate_limit import limiter
from app.core.security import create_state_token, verify_password
from app.db.session import AsyncSessionLocal
from app.models.refresh_token import RefreshToken
from app.models.user import User

NEW_PASSWORD = "Nueva1234!"


@pytest.fixture
def sent(monkeypatch):
    # The per-IP limits (3/minute on forgot-password) would trip across tests.
    monkeypatch.setattr(limiter, "enabled", False)
    mails = []
    monkeypatch.setattr(
        auth.email,
        "send_password_reset_email",
        lambda to, name, url, minutes: mails.append((to, url)),
    )
    return mails


def _token(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


async def test_same_answer_with_or_without_account(async_client, user_and_headers, sent):
    user, _ = user_and_headers
    known = await async_client.post("/auth/forgot-password", json={"email": user.email})
    unknown = await async_client.post("/auth/forgot-password", json={"email": "nadie@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert [to for to, _ in sent] == [user.email]


async def test_reset_changes_password_revokes_sessions_and_is_single_use(async_client, user_and_headers, sent):
    user, _ = user_and_headers
    await async_client.post("/auth/login", json={"email": user.email, "password": "Test1234!"})
    await async_client.post("/auth/forgot-password", json={"email": user.email})
    token = _token(sent[0][1])

    resp = await async_client.post("/auth/reset-password", json={"token": token, "password": NEW_PASSWORD})
    assert resp.status_code == 200, resp.text

    async with AsyncSessionLocal() as session:
        fresh = (await session.execute(select(User).where(User.id == user.id))).scalar_one()
        assert verify_password(NEW_PASSWORD, fresh.hashed_password)
        live = (
            await session.execute(
                select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            )
        ).scalars().all()
        assert live == []

    again = await async_client.post("/auth/reset-password", json={"token": token, "password": "Otra1234!"})
    assert again.status_code == 400
    login = await async_client.post("/auth/login", json={"email": user.email, "password": NEW_PASSWORD})
    assert login.status_code == 200


async def test_rejects_forged_or_wrong_purpose_tokens(async_client, user_and_headers, sent):
    user, _ = user_and_headers
    for token in ["basura", create_state_token(str(user.id), purpose="email_verify")]:
        resp = await async_client.post("/auth/reset-password", json={"token": token, "password": NEW_PASSWORD})
        assert resp.status_code == 400


async def test_new_password_follows_signup_rules(async_client, user_and_headers, sent):
    user, _ = user_and_headers
    await async_client.post("/auth/forgot-password", json={"email": user.email})
    resp = await async_client.post("/auth/reset-password", json={"token": _token(sent[0][1]), "password": "debil123"})
    assert resp.status_code == 422
