"""Integration tests for the applications router — regression coverage for
right-swipe -> applied (with applied_at stamped), pagination (limit/offset
+ total), the "undo" guard that only allows undoing a passed decision, and
the stale-applications count that powers the Pipeline nav badge."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.enums import JobSource
from app.models.job import Job
from app.scripts.check_stale_applications import STALE_AFTER_DAYS


async def _make_job(title: str) -> Job:
    async with AsyncSessionLocal() as session:
        job = Job(
            source=JobSource.manual,
            title=title,
            company="Acme",
            description="Build things.",
            requirements=[],
            responsibilities=[],
            skills_required=[],
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


async def test_swipe_right_creates_applied_application_with_timestamp(async_client, user_and_headers):
    _, headers = user_and_headers
    job = await _make_job("Swipe right job")

    resp = await async_client.post(
        f"/jobs/{job.id}/decision", headers=headers, json={"decision": "right"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "applied"
    assert body["applied_at"] is not None


async def test_swipe_left_creates_passed_application(async_client, user_and_headers):
    _, headers = user_and_headers
    job = await _make_job("Swipe left job")

    resp = await async_client.post(
        f"/jobs/{job.id}/decision", headers=headers, json={"decision": "left"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "passed"
    assert body["applied_at"] is None


async def test_applications_pagination_and_total(async_client, user_and_headers):
    _, headers = user_and_headers
    for i in range(3):
        job = await _make_job(f"Pagination job {i}")
        await async_client.post(f"/jobs/{job.id}/decision", headers=headers, json={"decision": "left"})

    resp = await async_client.get("/applications", headers=headers, params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] == 3

    resp2 = await async_client.get("/applications", headers=headers, params={"limit": 2, "offset": 2})
    assert len(resp2.json()["items"]) == 1


async def test_undo_only_allowed_on_passed(async_client, user_and_headers):
    _, headers = user_and_headers
    job = await _make_job("Undo guard job")

    decide_resp = await async_client.post(
        f"/jobs/{job.id}/decision", headers=headers, json={"decision": "right"}
    )
    application_id = decide_resp.json()["id"]

    resp = await async_client.delete(f"/applications/{application_id}", headers=headers)
    assert resp.status_code == 400


async def test_undo_removes_a_passed_application(async_client, user_and_headers):
    _, headers = user_and_headers
    job = await _make_job("Undo happy path job")

    decide_resp = await async_client.post(
        f"/jobs/{job.id}/decision", headers=headers, json={"decision": "left"}
    )
    application_id = decide_resp.json()["id"]

    resp = await async_client.delete(f"/applications/{application_id}", headers=headers)
    assert resp.status_code == 204

    get_resp = await async_client.get(f"/applications/{application_id}", headers=headers)
    assert get_resp.status_code == 404


async def test_stale_count_only_counts_old_unresolved_applications(async_client, user_and_headers):
    user, headers = user_and_headers
    old_job = await _make_job("Old applied job")
    recent_job = await _make_job("Recent applied job")

    decide_old = await async_client.post(
        f"/jobs/{old_job.id}/decision", headers=headers, json={"decision": "right"}
    )
    decide_recent = await async_client.post(
        f"/jobs/{recent_job.id}/decision", headers=headers, json={"decision": "right"}
    )

    async with AsyncSessionLocal() as session:
        old_app = (
            await session.execute(
                select(Application).where(Application.id == decide_old.json()["id"])
            )
        ).scalar_one()
        old_app.applied_at = datetime.now(timezone.utc) - timedelta(days=STALE_AFTER_DAYS + 1)
        recent_app = (
            await session.execute(
                select(Application).where(Application.id == decide_recent.json()["id"])
            )
        ).scalar_one()
        recent_app.applied_at = datetime.now(timezone.utc) - timedelta(days=1)
        await session.commit()

    resp = await async_client.get("/applications/stale-count", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
