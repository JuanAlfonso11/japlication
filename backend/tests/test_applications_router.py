"""Integration tests for the applications router — regression coverage for
right-swipe -> saved (only the detail page's mark_applied makes it applied,
with applied_at stamped), the "Activas" list Pipeline opens on, pagination
(limit/offset + total), the "undo" guard that only allows undoing a passed
decision, and the stale-applications count that powers the Pipeline nav
badge."""

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


async def test_swipe_right_only_saves_it(async_client, user_and_headers):
    """The card says "Guardar" and nothing is sent to the employer, so the
    swipe must not claim an application that never happened."""
    _, headers = user_and_headers
    job = await _make_job("Swipe right job")

    resp = await async_client.post(
        f"/jobs/{job.id}/decision", headers=headers, json={"decision": "right"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "saved"
    assert body["applied_at"] is None


async def test_mark_applied_is_what_stamps_an_application(async_client, user_and_headers):
    _, headers = user_and_headers
    job = await _make_job("Detail page apply job")

    resp = await async_client.post(
        f"/jobs/{job.id}/decision", headers=headers, json={"decision": "right", "mark_applied": True}
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


async def test_active_filter_leaves_out_finished_decisions(async_client, user_and_headers):
    _, headers = user_and_headers
    saved_job = await _make_job("Still in play")
    passed_job = await _make_job("Discarded")
    await async_client.post(f"/jobs/{saved_job.id}/decision", headers=headers, json={"decision": "right"})
    await async_client.post(f"/jobs/{passed_job.id}/decision", headers=headers, json={"decision": "left"})

    resp = await async_client.get("/applications", headers=headers, params={"active": "true"})
    assert resp.status_code == 200
    body = resp.json()
    # The total drives "N en total" in the header, so it has to be filtered too.
    assert body["total"] == 1
    assert [item["status"] for item in body["items"]] == ["saved"]


async def test_marking_applied_by_hand_stamps_applied_at(async_client, user_and_headers):
    """Pipeline's status dropdown is the other route to a real application —
    without applied_at the stale-application reminder can never see it."""
    _, headers = user_and_headers
    job = await _make_job("Marked applied by hand")
    decide_resp = await async_client.post(
        f"/jobs/{job.id}/decision", headers=headers, json={"decision": "right"}
    )
    application_id = decide_resp.json()["id"]

    resp = await async_client.patch(
        f"/applications/{application_id}", headers=headers, json={"status": "applied"}
    )
    assert resp.status_code == 200
    assert resp.json()["applied_at"] is not None


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
        f"/jobs/{old_job.id}/decision", headers=headers, json={"decision": "right", "mark_applied": True}
    )
    decide_recent = await async_client.post(
        f"/jobs/{recent_job.id}/decision", headers=headers, json={"decision": "right", "mark_applied": True}
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
