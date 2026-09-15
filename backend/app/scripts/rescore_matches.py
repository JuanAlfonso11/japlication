"""Recalcula los match ya guardados, tras un arreglo del motor de puntuacion.

Por que hace falta
------------------
El score se calcula una vez, al descubrir la vacante, y se guarda. Eso es lo
correcto -- recalcular en cada lectura seria caro y haria que el numero
bailara solo. Pero significa que un fallo en el calculo queda congelado en
cada fila que se puntuo mientras el fallo existia.

Paso con dos: la palabra "plus" reclasificaba como deseables todas las
habilidades obligatorias (el score subia y "lo que te falta" salia vacio), y
el extractor de requisitos se tragaba 40 lineas de "Sobre nosotros". Arreglar
el codigo arregla el futuro; esto arregla el pasado.

Volver a puntuar NO basta
-------------------------
Medido: recalcular los 210 match dejaba los 210 exactamente igual. El motivo
es que el fallo no estaba en el calculo, estaba en la EXTRACCION: "plus" y el
extractor de secciones corren al importar la vacante, y su resultado quedo
guardado en jobs.skills_required y jobs.requirements. Volver a puntuar lee esas
columnas, asi que recalcula sobre el dato ya contaminado y sale lo mismo.

Por eso --reparse vuelve a analizar la descripcion guardada de cada vacante
con el extractor ya arreglado, y solo despues puntua. Esa es la unica version
que arregla el pasado de verdad.

Lo que NO toca
--------------
Las decisiones ya tomadas. Una vacante que descartaste sigue descartada, y
`applications.match_score` -- el numero que tenias delante cuando decidiste --
se queda como estaba: es el registro de por que hiciste lo que hiciste, y
reescribirlo seria falsear tu propio historial.

Uso:
    docker compose exec -T backend python -m app.scripts.rescore_matches --dry-run
    docker compose exec -T backend python -m app.scripts.rescore_matches
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.career_profile import CareerProfile
from app.models.job import Job
from app.models.job_match import JobMatch
from app.services.job_importer import _build_skills_required, _extract_section, SECTION_HEADERS
from app.services.match_engine import compute_and_persist_match


def _reparse(job: Job) -> tuple[list, list, list]:
    """Vuelve a extraer de la descripcion guardada, con el extractor arreglado."""
    texto = job.description or ""
    return (
        _build_skills_required(texto),
        _extract_section(texto, SECTION_HEADERS["requirements"]) or [],
        _extract_section(texto, SECTION_HEADERS["responsibilities"]) or [],
    )


async def run(dry_run: bool, threshold: float, reparse: bool) -> None:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(JobMatch))).scalars().all()
        print(f"{len(rows)} match guardados\n")

        profiles: dict = {}
        subidas = bajadas = igual = 0
        movidas: list[tuple[str, float, float]] = []

        for row in rows:
            if row.user_id not in profiles:
                profiles[row.user_id] = (
                    await db.execute(
                        select(CareerProfile).where(CareerProfile.user_id == row.user_id)
                    )
                ).scalar_one_or_none()
            profile = profiles[row.user_id]
            if profile is None:
                continue
            job = (await db.execute(select(Job).where(Job.id == row.job_id))).scalar_one_or_none()
            if job is None:
                continue

            if reparse:
                skills, requisitos, responsabilidades = _reparse(job)
                if not dry_run:
                    job.skills_required = skills
                    if requisitos:
                        job.requirements = requisitos
                    if responsabilidades:
                        job.responsibilities = responsabilidades
                    await db.flush()
                else:
                    # En simulacro se puntua contra el objeto en memoria sin
                    # guardarlo, para ver el efecto real sin tocar la fila.
                    job.skills_required = skills
                    if requisitos:
                        job.requirements = requisitos

            antes = float(row.overall_score)
            if dry_run:
                # Sin persistir: se recalcula y se compara, nada mas.
                from app.services.match_engine import compute_match

                despues = float(compute_match(profile, job, use_llm=False)["overall_score"])
            else:
                # use_llm=False igual que el barrido: esto recorre cientos de
                # filas y una llamada a Anthropic por cada una costaria dinero
                # real sin mejorar la comparacion.
                resultado = await compute_and_persist_match(
                    profile, job, row.user_id, db, use_llm=False
                )
                despues = float(resultado.overall_score)

            delta = despues - antes
            if abs(delta) < 0.05:
                igual += 1
            elif delta > 0:
                subidas += 1
            else:
                bajadas += 1
            if abs(delta) >= threshold:
                movidas.append((f"{job.title} — {job.company}", antes, despues))

        print(f"suben: {subidas}   bajan: {bajadas}   igual: {igual}")
        print(f"\ncambios de {threshold:g} puntos o mas ({len(movidas)}):")
        for titulo, antes, despues in sorted(movidas, key=lambda m: m[2] - m[1], reverse=True)[:25]:
            print(f"  {antes:5.1f} -> {despues:5.1f}  ({despues - antes:+5.1f})  {titulo[:58]}")
        if dry_run:
            await db.rollback()
            print("\n(simulacro: no se guardo nada)")
        else:
            await db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="calcula y compara sin guardar")
    parser.add_argument("--threshold", type=float, default=8.0, help="cambio minimo que se lista")
    parser.add_argument(
        "--reparse",
        action="store_true",
        help="vuelve a extraer habilidades y requisitos de la descripcion antes de puntuar",
    )
    args = parser.parse_args()
    asyncio.run(run(args.dry_run, args.threshold, args.reparse))


if __name__ == "__main__":
    main()
