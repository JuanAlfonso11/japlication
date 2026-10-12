"""Banco de prueba del agente de aplicacion (puerta de la fase 2).

Arma borradores de formularios REALES de Greenhouse con un perfil, sin enviar
nada, y deja un reporte para calificarlos campo por campo. La puerta de la
fase 2 es que el 90 % de los campos que el agente llena esten bien.

    python -m app.scripts.apply_bench --facts /app/runtime/apply_bench/profile.json \\
        --out /app/runtime/apply_bench [--no-ai] [--total 20]

`--facts` es un JSON {"user": {...}, "profile": {...}} con la forma de las
tablas users y career_profiles (ver facts.py). Sin base de datos a proposito:
asi el banco corre igual en el entorno de desarrollo, que no tiene tu perfil.

Elige las ofertas solo: de cada tablero del banco, las de ingenieria que no son
senior, primero las abiertas a remoto/Americas/LATAM. Las lee por la API
publica; no abre ningun navegador ni toca ningun formulario.

Salida:
  * bench.json -- los borradores completos.
  * bench.md   -- una tabla por formulario con una columna "¿Bien?" para
                  marcar cada campo que el agente lleno.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.apply_agent.draft import FILLED, NEEDS_USER, REVIEW_REASONS, build_draft
from app.services.apply_agent.facts import build_facts, missing_for_agent
from app.services.apply_agent.greenhouse import FormUnavailable, fetch_greenhouse_form

#: Los 8 tableros de Greenhouse del banco (ver tasks/agente-aplicacion.md):
#: los que mas vacantes tecnicas remotas tenian al medirlo el 2026-10-12.
BENCH_BOARDS = ["canonical", "amplemarket", "anthropic", "gitlab", "coinbase", "reddit", "twilio", "grafanalabs"]

_TECH = re.compile(r"\b(engineer|developer|software|backend|full[\s-]?stack|machine learning|ml|ai|data)\b", re.I)
_SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|manager|director|head|architect|vp|iii|iv)\b", re.I)
_OPEN = re.compile(r"(latam|latin america|americas|worldwide|anywhere|global|remote|home based)", re.I)


async def _board_jobs(board: str) -> list[dict[str, Any]]:
    from app.services.external_jobs import http as external_http

    resp = await external_http.get("greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs")
    if getattr(resp, "status_code", 200) != 200:
        return []
    return (resp.json() or {}).get("jobs") or []


def _pick(jobs: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    tecnicas = [j for j in jobs if _TECH.search(j.get("title") or "") and not _SENIOR.search(j.get("title") or "")]
    abiertas = [j for j in tecnicas if _OPEN.search((j.get("location") or {}).get("name") or "")]
    resto = [j for j in tecnicas if j not in abiertas]
    return (abiertas + resto)[:n]


def _cell(value: Any) -> str:
    texto = "" if value is None else str(value)
    texto = " ".join(texto.split()).replace("|", "/")
    return texto if len(texto) <= 160 else texto[:157] + "..."


def _markdown(resultados: list[dict[str, Any]], resumen: dict[str, Any]) -> str:
    lineas = [
        "# Banco de prueba del agente de aplicación",
        "",
        f"Generado: {resumen['generated_at']} · IA: {'sí' if resumen['ai'] else 'no'} · "
        f"Formularios: {resumen['forms']} · Campos llenados por el agente: {resumen['filled']}",
        "",
        "Marca la columna **¿Bien?** con `s` o `n` en cada campo con estado `filled`. "
        "La puerta de la fase 2 es que al menos el 90 % de esos campos estén bien.",
        "",
    ]
    if resumen["profile_missing"]:
        lineas += ["**Al perfil le falta:** " + ", ".join(resumen["profile_missing"]), ""]
    for r in resultados:
        if r.get("error"):
            lineas += [f"## {r['board']} · {r['job_id']}", "", f"No se pudo leer: {r['error']}", ""]
            continue
        d = r["draft"]
        s = d["stats"]
        lineas += [
            f"## {d['company']} · {d['title']}",
            "",
            f"[Formulario]({d['url']}) · llenados {s['filled']}/{s['total']} · obligatorios llenados "
            f"{s['required_filled']}/{s['required']} · por IA {s['by_ai']} · "
            f"apto para automático: {'sí' if d['auto_eligible'] else 'no'}",
            "",
        ]
        if d["review_reasons"]:
            lineas += ["Motivos de revisión: " + "; ".join(REVIEW_REASONS[c] for c in d["review_reasons"]), ""]
        lineas += ["| ¿Bien? | Pregunta | Oblig. | Clase | Estado | Respuesta | Fuente | Nota |", "|---|---|---|---|---|---|---|---|"]
        for f in d["fields"]:
            marca = "" if f["status"] == FILLED else "—"
            lineas.append(
                f"| {marca} | {_cell(f['label'])} | {'sí' if f['required'] else ''} | {f['kind']} | {f['status']} | "
                f"{_cell(f['display'])} | {f['source']} | {_cell(f['reason'])} |"
            )
        lineas.append("")
    return "\n".join(lineas)


async def run(facts_path: Path, out: Path, use_ai: bool, total: int) -> dict[str, Any]:
    datos = json.loads(facts_path.read_text(encoding="utf-8"))
    facts = build_facts(datos.get("user") or {}, datos.get("profile") or {})

    por_tablero = max(1, -(-total // len(BENCH_BOARDS)))
    elegidas: list[tuple[str, dict[str, Any]]] = []
    for board in BENCH_BOARDS:
        for job in _pick(await _board_jobs(board), por_tablero):
            elegidas.append((board, job))
    elegidas = elegidas[:total]

    resultados = []
    for board, job in elegidas:
        try:
            form = await fetch_greenhouse_form(board, str(job["id"]))
            draft = await build_draft(form, facts, use_ai=use_ai)
            resultados.append({"board": board, "job_id": job["id"], "draft": draft.to_dict()})
        except FormUnavailable as exc:
            resultados.append({"board": board, "job_id": job["id"], "error": str(exc)})

    borradores = [r["draft"] for r in resultados if "draft" in r]
    resumen = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "ai": use_ai,
        "forms": len(borradores),
        "errors": len(resultados) - len(borradores),
        "fields": sum(d["stats"]["total"] for d in borradores),
        "filled": sum(d["stats"]["filled"] for d in borradores),
        "by_ai": sum(d["stats"]["by_ai"] for d in borradores),
        "needs_user": sum(1 for d in borradores for f in d["fields"] if f["status"] == NEEDS_USER),
        "auto_eligible": sum(1 for d in borradores if d["auto_eligible"]),
        "ai_policy": sum(1 for d in borradores if d["ai_policy"]),
        "profile_missing": missing_for_agent(facts),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "bench.json").write_text(
        json.dumps({"summary": resumen, "results": resultados}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (out / "bench.md").write_text(_markdown(resultados, resumen), encoding="utf-8")
    return resumen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--total", type=int, default=20)
    args = parser.parse_args()
    resumen = asyncio.run(run(args.facts, args.out, not args.no_ai, args.total))
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
