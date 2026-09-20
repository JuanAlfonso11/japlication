"""Sigue cada vacante guardada hasta su formulario real y lo anota.

Ninguna source_url apunta al formulario: todas apuntan al listado del portal.
Este script da ese salto una vez por vacante, para que no haya que darlo a
mano cada vez que se va a postular. Ver app/services/apply_target.py.

Uso:
    docker compose exec -T backend python -m app.scripts.resolve_apply_targets --limit 20
    docker compose exec -T backend python -m app.scripts.resolve_apply_targets        # todas
    docker compose exec -T backend python -m app.scripts.resolve_apply_targets --recheck
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.job import Job
from app.services.apply_target import resolve_apply_target

#: Tres a la vez y un respiro entre tandas. Esto sale a servidores de terceros
#: que no han pedido nada: ir en paralelo a lo ancho de 252 vacantes es
#: exactamente como se consigue que un portal bloquee la IP.
_CONCURRENCIA = 3
_PAUSA_SEGUNDOS = 0.5


async def run(limit: int | None, recheck: bool) -> None:
    async with AsyncSessionLocal() as db:
        stmt = select(Job).where(Job.source_url.isnot(None))
        if not recheck:
            stmt = stmt.where(Job.apply_checked_at.is_(None))
        stmt = stmt.order_by(Job.created_at.desc())
        if limit:
            stmt = stmt.limit(limit)
        jobs = (await db.execute(stmt)).scalars().all()

    print(f"{len(jobs)} vacantes por resolver\n")
    if not jobs:
        return

    semaforo = asyncio.Semaphore(_CONCURRENCIA)
    resultados: list[tuple[Job, object]] = []

    async def uno(job: Job):
        async with semaforo:
            target = await resolve_apply_target(job.source_url or "", job.description or "")
            await asyncio.sleep(_PAUSA_SEGUNDOS)
            return job, target

    for i in range(0, len(jobs), 20):
        tanda = jobs[i : i + 20]
        resultados.extend(await asyncio.gather(*[uno(j) for j in tanda]))
        print(f"  {min(i + 20, len(jobs))}/{len(jobs)}")

    ahora = datetime.now(timezone.utc)
    conteo: Counter = Counter()
    con_correo = 0

    async with AsyncSessionLocal() as db:
        for job, target in resultados:
            fila = (await db.execute(select(Job).where(Job.id == job.id))).scalar_one_or_none()
            if fila is None:
                continue
            fila.apply_url = target.url
            fila.apply_ats = target.ats
            fila.apply_email = target.email
            fila.apply_note = target.note
            fila.apply_checked_at = ahora
            conteo[target.ats or ("pagina propia" if target.url else "sin resolver")] += 1
            if target.email:
                con_correo += 1
        await db.commit()

    print("\ndestino encontrado:")
    for nombre, n in conteo.most_common():
        print(f"  {nombre:<18} {n:>4}")
    resueltas = sum(n for k, n in conteo.items() if k != "sin resolver")
    print(f"\ncon formulario: {resueltas}/{len(resultados)}")
    print(f"con correo para postular: {con_correo}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="solo las N mas recientes")
    parser.add_argument("--recheck", action="store_true", help="revisa tambien las ya miradas")
    args = parser.parse_args()
    asyncio.run(run(args.limit, args.recheck))


if __name__ == "__main__":
    main()
