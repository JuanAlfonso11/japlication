"""Proves the error log actually captures — and actually stays quiet.

A logging system nobody verifies is worse than none: it produces the feeling
of coverage without the coverage. These tests exercise the real middleware
through the real app, including the two properties that matter most beyond
"it writes a row": that it never stores credentials, and that it doesn't
bury real failures under routine 4xx noise.
"""

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.error_log import ErrorLog


# A route that blows up, mounted only for these tests. Reaching the
# middleware needs a genuine unhandled exception, and deliberately breaking a
# real endpoint to get one would be far more fragile.
@app.get("/api/v1/__boom__")
async def _boom():
    raise RuntimeError("explosion de prueba")


@app.post("/api/v1/__boom_with_body__")
async def _boom_with_body(payload: dict):
    raise RuntimeError("explosion con cuerpo")


async def _stored_errors() -> list[ErrorLog]:
    async with AsyncSessionLocal() as session:
        return list(
            (await session.execute(select(ErrorLog).order_by(ErrorLog.created_at.desc())))
            .scalars()
            .all()
        )


async def test_an_unhandled_exception_is_recorded_with_its_traceback(async_client):
    resp = await async_client.get("/__boom__")

    assert resp.status_code == 500
    body = resp.json()
    assert "request_id" in body

    rows = await _stored_errors()
    assert len(rows) == 1
    row = rows[0]
    assert row.source == "backend"
    assert row.kind == "RuntimeError"
    assert "explosion de prueba" in row.message
    # The traceback is the whole point — without it you know something broke
    # but not where.
    assert row.stack and "RuntimeError" in row.stack
    assert row.method == "GET"
    assert row.path.endswith("/__boom__")
    assert row.status_code == 500


async def test_the_id_the_user_sees_is_the_id_that_was_stored(async_client):
    """Otherwise "salió el código a1b2c3" is unlookupable and the whole
    correlation scheme is decorative."""
    resp = await async_client.get("/__boom__")

    shown = resp.json()["request_id"]
    assert resp.headers.get("x-request-id") == shown

    rows = await _stored_errors()
    assert rows[0].request_id == shown


async def test_the_request_body_is_never_stored(async_client):
    """The guard that keeps a debugging aid from becoming a credential leak:
    the first thing a POST to /auth/login carries is a password."""
    secret = "sup3r-s3cret-passw0rd"

    resp = await async_client.post(
        "/__boom_with_body__", json={"password": secret, "email": "a@b.c"}
    )
    assert resp.status_code == 500

    rows = await _stored_errors()
    assert len(rows) == 1
    stored = " ".join(
        str(v) for v in (rows[0].message, rows[0].stack, rows[0].path, rows[0].method) if v
    )
    assert secret not in stored


async def test_successful_requests_are_not_logged(async_client):
    resp = await async_client.get("/../health")
    assert resp.status_code in (200, 404)
    assert await _stored_errors() == []


async def test_routine_4xx_responses_are_not_logged(async_client):
    """A 401 on an expired token is the app working. Recording those buries
    the real failures under thousands of rows nobody reads."""
    unauth = await async_client.get("/profile")
    assert unauth.status_code == 401

    not_found = await async_client.get("/jobs/00000000-0000-0000-0000-000000000000")
    assert not_found.status_code in (401, 404)

    assert await _stored_errors() == []


async def test_every_response_carries_a_correlation_id(async_client, user_and_headers):
    """Not only failures: having the id on a successful response is what
    lets a user report "this screen was wrong" and still be traceable."""
    _, headers = user_and_headers
    resp = await async_client.get("/system/status", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("x-request-id")


# --------------------------------------------------------------------------
# frontend error reporting
# --------------------------------------------------------------------------


async def test_the_app_can_report_its_own_crashes(async_client, user_and_headers):
    user, headers = user_and_headers

    resp = await async_client.post(
        "/system/client-errors",
        headers=headers,
        json={
            "kind": "TypeError",
            "message": "Cannot read properties of undefined",
            "stack": "at SwipeCard (SwipeCard.tsx:42)",
            "url": "/jobs/abc",
        },
    )
    assert resp.status_code == 204

    rows = await _stored_errors()
    assert len(rows) == 1
    assert rows[0].source == "frontend"
    assert rows[0].kind == "TypeError"
    assert "SwipeCard" in rows[0].stack
    assert rows[0].user_id == user.id


async def test_reporting_a_crash_requires_a_session(async_client):
    resp = await async_client.post(
        "/system/client-errors", json={"message": "anonimo"}
    )
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"message": ""},
        {"message": "x" * 5000},
        {"message": "ok", "stack": "y" * 20000},
    ],
)
async def test_client_reports_are_length_capped(async_client, user_and_headers, payload):
    """This endpoint is reachable by anything the app runs on; an uncapped
    stack is a free way to fill the disk."""
    _, headers = user_and_headers
    resp = await async_client.post("/system/client-errors", headers=headers, json=payload)
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# reading them back
# --------------------------------------------------------------------------


async def test_listing_errors_requires_authentication(async_client):
    assert (await async_client.get("/system/errors")).status_code == 401


async def test_errors_come_back_newest_first(async_client, user_and_headers):
    _, headers = user_and_headers
    for i in range(3):
        await async_client.post(
            "/system/client-errors", headers=headers, json={"message": f"error {i}"}
        )

    resp = await async_client.get("/system/errors", headers=headers)
    assert resp.status_code == 200
    messages = [e["message"] for e in resp.json()]
    assert messages == ["error 2", "error 1", "error 0"]


async def test_errors_can_be_filtered_by_side(async_client, user_and_headers):
    _, headers = user_and_headers
    await async_client.post("/system/client-errors", headers=headers, json={"message": "del app"})
    await async_client.get("/__boom__")

    frontend_only = (await async_client.get("/system/errors?source=frontend", headers=headers)).json()
    assert [e["source"] for e in frontend_only] == ["frontend"]

    backend_only = (await async_client.get("/system/errors?source=backend", headers=headers)).json()
    assert [e["source"] for e in backend_only] == ["backend"]
