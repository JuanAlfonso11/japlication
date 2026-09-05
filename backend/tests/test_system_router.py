"""Integration tests for /system/heartbeat + /system/status — regression
coverage for the mandatory heartbeat secret (previously optional, silently
accepting unauthenticated callers when unset)."""

from app.core.config import settings


async def test_heartbeat_rejects_missing_secret(async_client, monkeypatch):
    monkeypatch.setattr(settings, "SYSTEM_HEARTBEAT_SECRET", "correct-secret")
    resp = await async_client.post(
        "/system/heartbeat", json={"job_name": "test_job", "status": "ok", "detail": ""}
    )
    assert resp.status_code == 401


async def test_heartbeat_rejects_wrong_secret(async_client, monkeypatch):
    monkeypatch.setattr(settings, "SYSTEM_HEARTBEAT_SECRET", "correct-secret")
    resp = await async_client.post(
        "/system/heartbeat",
        json={"job_name": "test_job", "status": "ok", "detail": ""},
        headers={"X-Heartbeat-Secret": "wrong-secret"},
    )
    assert resp.status_code == 401


async def test_heartbeat_accepts_correct_secret_and_upserts(async_client, monkeypatch, user_and_headers):
    monkeypatch.setattr(settings, "SYSTEM_HEARTBEAT_SECRET", "correct-secret")
    _, auth_headers = user_and_headers

    resp = await async_client.post(
        "/system/heartbeat",
        json={"job_name": "test_job", "status": "ok", "detail": "all good"},
        headers={"X-Heartbeat-Secret": "correct-secret"},
    )
    assert resp.status_code == 204

    status_resp = await async_client.get("/system/status", headers=auth_headers)
    assert status_resp.status_code == 200
    jobs = {row["job_name"]: row for row in status_resp.json()}
    assert jobs["test_job"]["last_status"] == "ok"
