"""Integration tests for GET /jobs — regression coverage for the batched
JobMatch fetch (fixed from an N+1 per-job query) and for pagination
(limit/offset + total)."""

from app.db.session import AsyncSessionLocal
from app.models.career_profile import CareerProfile
from app.models.job import Job
from app.models.enums import JobSource
from app.services.match_engine import compute_and_persist_match


async def _make_job(title: str = "Backend Engineer") -> Job:
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


async def test_list_jobs_returns_batched_match_data(async_client, user_and_headers):
    user, headers = user_and_headers
    matched_job = await _make_job("Has a match")
    unmatched_job = await _make_job("No match yet")

    async with AsyncSessionLocal() as session:
        profile = CareerProfile(user_id=user.id, skills=[], experience=[])
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        # use_llm=False: this test verifies the batched-match response
        # shape, not semantic scoring quality — keep it offline/free/fast.
        await compute_and_persist_match(profile, matched_job, user.id, session, use_llm=False)

    resp = await async_client.get("/jobs", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    by_id = {item["id"]: item for item in body["items"]}

    assert by_id[str(matched_job.id)]["match"] is not None
    assert by_id[str(matched_job.id)]["match"]["overall_score"] >= 0
    assert by_id[str(unmatched_job.id)]["match"] is None


async def test_list_jobs_pagination_total(async_client, user_and_headers):
    _, headers = user_and_headers
    for i in range(3):
        await _make_job(f"Job {i}")

    resp = await async_client.get("/jobs", headers=headers, params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] == 3

    resp2 = await async_client.get("/jobs", headers=headers, params={"limit": 2, "offset": 2})
    assert len(resp2.json()["items"]) == 1
