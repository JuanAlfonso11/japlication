"""Comprueba si las vacantes pendientes siguen abiertas y marca las cerradas.

Solo mira las que todavia pueden importar: en la cola de swipe o guardadas.
Una a la que ya postulaste, o que descartaste, no gana nada con saberlo.
Ver app/services/liveness.py.

Uso:
    docker compose exec -T backend python -m app.scripts.check_liveness --limit 20
    docker compose exec -T backend python -m app.scripts.check_liveness          # todas las pendientes
    docker compose exec -T backend python -m app.scripts.check_liveness --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, exists, or_, select

from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.job import Job
from app.services.liveness import check_liveness

#: Igual que resolve_apply_targets: esto sale a servidores de terceros.
_CONCURRENCIA = 3
_PAUSA_SEGUNDOS = 0.5
#: Una oferta abierta hoy casi seguro sigue abierta manana.
RECHECK_AFTER = timedelta(days=3)

#: Estados que ya no dependen de que la oferta siga abierta.
_TERMINADOS = (
    ApplicationStatus.applied,
    ApplicationStatus.interviewing,
    ApplicationStatus.offer,
    ApplicationStatus.rejected,
    ApplicationStatus.withdrawn,
    ApplicationStatus.passed,
)


async def run(limit: int | None, dry_run: bool = False) -> Counter:
    ahora = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        terminada = exists().where(
            and_(Application.job_id == Job.id, Application.status.in_(_TERMINADOS))
        )
        stmt = (
            select(Job.id, Job.source_url, Job.apply_url)
            .where(Job.closed_at.is_(None))
            .where(or_(Job.source_url.isnot(None), Job.apply_url.isnot(None)))
            .where(~terminada)
            .where(or_(Job.liveness_checked_at.is_(None), Job.liveness_checked_at < ahora - RECHECK_AFTER))
            .order_by(Job.liveness_checked_at.asc().nulls_first(), Job.created_at.desc())
        )
        if limit:
            stmt = stmt.limit(limit)
        filas = (await db.execute(stmt)).all()

    print(f"{len(filas)} vacantes por comprobar")
    conteo: Counter = Counter()
    if not filas:
        return conteo

    semaforo = asyncio.Semaphore(_CONCURRENCIA)

    async def una(fila):
        async with semaforo:
            resultado = await check_liveness(fila.source_url, fila.apply_url)
            await asyncio.sleep(_PAUSA_SEGUNDOS)
            return fila.id, resultado

    resultados = await asyncio.gather(*[una(f) for f in filas])

    async with AsyncSessionLocal() as db:
        for job_id, resultado in resultados:
            conteo[resultado.status] += 1
            if resultado.status == "closed":
                print(f"  cerrada: {job_id} - {resultado.reason}")
            if dry_run:
                continue
            job = await db.get(Job, job_id)
            if job is None:
                continue
            job.liveness_checked_at = ahora
            if resultado.status == "closed":
                job.closed_at = ahora
        if not dry_run:
            await db.commit()

    print(" ".join(f"{k}={v}" for k, v in sorted(conteo.items())))
    return conteo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="no escribe nada")
    args = parser.parse_args()
    asyncio.run(run(args.limit, args.dry_run))


if __name__ == "__main__":
    main()
