"""Limpia los duplicados que entraron ANTES de que existiera el dedupe.

`app/services/job_dedupe.py` impide que la busqueda agregada vuelva a
importar la misma vacante varias veces, pero no toca lo ya guardado. En la
base real quedaron grupos de filas identicas de cuando el sweep importaba
cada copia por separado, y varias seguian en la cola de swipe: el usuario
tenia que decidir dos veces sobre el mismo empleo.

La regla de borrado es deliberadamente conservadora, porque borrar un job
arrastra en cascada sus job_matches y applications:

  * Una copia sobre la que YA se decidio algo (guardada, aplicada,
    entrevistando, pasada...) nunca se borra. Eso es historial del usuario
    y vale mas que la prolijidad.
  * Solo se borran copias sin ninguna application asociada, es decir
    vacantes que nadie llego a ver en la cola.
  * Si todas las copias de un grupo estan sin decidir, se conserva una: la
    de descripcion mas larga (la mas informativa), y ante empate la mas
    reciente.

Por defecto NO borra nada: hay que pasar --apply. Un script de limpieza que
borra por el solo hecho de ejecutarse es como se pierden datos por accidente.

Uso:
    docker compose run --rm backend python -m app.scripts.dedupe_existing_jobs
    docker compose run --rm backend python -m app.scripts.dedupe_existing_jobs --apply
"""

import argparse
import asyncio
from collections import defaultdict

from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.job import Job
from app.services.job_dedupe import _normalize_text


async def _run(apply_changes: bool) -> None:
    async with AsyncSessionLocal() as session:
        jobs = (await session.execute(select(Job))).scalars().all()

        # Que jobs tienen alguna decision tomada.
        decided_ids = set(
            (await session.execute(select(Application.job_id).distinct())).scalars().all()
        )

        groups: dict[tuple[str, str], list[Job]] = defaultdict(list)
        for job in jobs:
            company = _normalize_text(job.company)
            title = _normalize_text(job.title)
            if company and title:
                groups[(company, title)].append(job)

        to_delete: list[Job] = []
        for (company, title), copies in groups.items():
            if len(copies) < 2:
                continue

            undecided = [j for j in copies if j.id not in decided_ids]
            decided = [j for j in copies if j.id in decided_ids]

            if decided:
                # Ya hay al menos una copia con historial: se conservan todas
                # esas y se borran unicamente las que nadie llego a ver.
                removable = undecided
            else:
                # Ninguna decidida: conservar la mas informativa.
                keeper = sorted(
                    undecided,
                    key=lambda j: (len(j.description or ""), j.created_at),
                    reverse=True,
                )[0]
                removable = [j for j in undecided if j.id != keeper.id]

            if removable:
                print(f"  {title[:46]!r} @ {company[:24]!r}: {len(copies)} copias "
                      f"({len(decided)} con historial) -> se borran {len(removable)}")
                to_delete.extend(removable)

        if not to_delete:
            print("No hay duplicados que limpiar.")
            return

        print(f"\nTotal a borrar: {len(to_delete)} filas duplicadas sin decidir.")

        if not apply_changes:
            print("\n(simulacion — no se borro nada. Pasa --apply para ejecutarlo.)")
            return

        await session.execute(delete(Job).where(Job.id.in_([j.id for j in to_delete])))
        await session.commit()
        print(f"Listo: {len(to_delete)} filas borradas.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Ejecuta el borrado. Sin esta bandera solo simula.",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.apply))


if __name__ == "__main__":
    main()
