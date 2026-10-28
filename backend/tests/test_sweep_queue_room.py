"""El tope del barrido (jobs._undecided_queue_size) cuenta lo mismo que Inicio
ensena, y una cola vieja que nadie desliza no bloquea las vacantes nuevas.

Regresion: la cola de Juan tenia 30 vacantes del 10 de octubre sin decidir; el
barrido veia la cola "llena", importaba 0 cada 2 horas y nunca avisaba.
"""

from datetime import datetime, timedelta, timezone

from app.api.v1.routers.jobs import _HOME_QUEUE_TARGET, _undecided_queue_size
from app.db.session import AsyncSessionLocal
from app.models.enums import JobSource
from app.models.job import Job
from app.models.job_match import JobMatch


async def _queued(user_id, title, **job_fields):
    async with AsyncSessionLocal() as session:
        job = Job(source=JobSource.manual, title=title, company="Acme", description="x",
                  requirements=[], responsibilities=[], skills_required=[], **job_fields)
        session.add(job)
        await session.flush()
        session.add(JobMatch(user_id=user_id, job_id=job.id, overall_score=80))
        await session.commit()


async def test_only_fresh_open_jobs_take_room(user_and_headers):
    user, _ = user_and_headers
    ahora = datetime.now(timezone.utc)
    await _queued(user.id, "fresca")
    await _queued(user.id, "cerrada", closed_at=ahora)
    await _queued(user.id, "vencida", deadline=(ahora - timedelta(days=1)).date())
    await _queued(user.id, "vieja", created_at=ahora - timedelta(days=20))

    async with AsyncSessionLocal() as db:
        assert await _undecided_queue_size(user.id, db) == 1


async def test_a_full_but_stale_queue_leaves_room(user_and_headers):
    user, _ = user_and_headers
    viejo = datetime.now(timezone.utc) - timedelta(days=17)
    for i in range(_HOME_QUEUE_TARGET):
        await _queued(user.id, f"vieja {i}", created_at=viejo)
    async with AsyncSessionLocal() as db:
        assert await _undecided_queue_size(user.id, db) == 0
