"""¿Sigue abierta la oferta? (services/liveness.py, scripts/check_liveness.py)

Sin red: se sustituyen la llamada a la API del ATS y la descarga de la pagina.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.enums import ApplicationStatus, JobSource
from app.models.job import Job
from app.scripts import check_liveness as script
from app.services import ats_boards, liveness
from app.services.job_importer import JobImportError, JobPostingGone


@pytest.fixture
def api(monkeypatch):
    llamadas = []
    respuestas = {}

    async def fake_status(provider, url):
        llamadas.append(url)
        return respuestas.get(provider, 200)

    monkeypatch.setattr(liveness, "_api_status", fake_status)
    return SimpleNamespace(llamadas=llamadas, respuestas=respuestas)


async def test_greenhouse_por_api(api):
    url = "https://boards.greenhouse.io/acme/jobs/123"
    assert (await liveness.check_liveness(url)).status == "open"
    assert api.llamadas == ["https://boards-api.greenhouse.io/v1/boards/acme/jobs/123"]
    api.respuestas["greenhouse"] = 404
    assert (await liveness.check_liveness(url)).status == "closed"
    # Un 500 no es "cerrada": no se sabe.
    api.respuestas["greenhouse"] = 503
    assert (await liveness.check_liveness(url)).status == "unknown"


async def test_lever_usa_apply_url_antes_que_el_portal(api):
    api.respuestas["lever"] = 404
    r = await liveness.check_liveness(
        "https://jobicy.com/jobs/1",
        "https://jobs.lever.co/beta/0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b/apply",
    )
    assert r.status == "closed"
    assert api.llamadas == ["https://api.lever.co/v0/postings/beta/0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"]


async def test_ashby_por_tablero(monkeypatch):
    uid = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
    tablero = [{"id": uid}]

    async def fake_board(ats, slug):
        return tablero

    monkeypatch.setattr(ats_boards, "_fetch_board", fake_board)
    url = f"https://jobs.ashbyhq.com/gamma/{uid}"
    assert (await liveness.check_liveness(url)).status == "open"
    tablero[:] = [{"id": "otra"}]
    assert (await liveness.check_liveness(url)).status == "closed"
    # Tablero vacio: la empresa pudo cambiar de ATS. No basta para cerrarla.
    tablero[:] = []
    assert (await liveness.check_liveness(url)).status == "unknown"


@pytest.mark.parametrize(
    "html, esperado",
    [
        ("<h1>Backend Engineer</h1><p>Apply now</p>", "open"),
        ("<p>This job is no longer accepting applications.</p>", "closed"),
        ("<p>This position has been filled.</p>", "closed"),
        ("<p>Esta vacante ya no está disponible.</p>", "closed"),
        # Una palabra suelta no basta.
        ("<footer>Office closed on holidays</footer><p>Apply</p>", "open"),
    ],
)
async def test_pagina_generica(monkeypatch, html, esperado):
    async def fake_fetch(url):
        return html, url

    monkeypatch.setattr(liveness, "fetch_html_with_url", fake_fetch)
    assert (await liveness.check_liveness("https://empresa.example/jobs/1")).status == esperado


async def test_404_y_errores_de_red(monkeypatch):
    async def gone(url):
        raise JobPostingGone(404)

    async def caida(url):
        raise JobImportError("No pudimos leer esa vacante. Prueba con «Pegar manualmente».")

    monkeypatch.setattr(liveness, "fetch_html_with_url", gone)
    assert (await liveness.check_liveness("https://empresa.example/jobs/1")).status == "closed"
    monkeypatch.setattr(liveness, "fetch_html_with_url", caida)
    assert (await liveness.check_liveness("https://empresa.example/jobs/1")).status == "unknown"


async def test_portales_con_sesion_no_se_marcan(monkeypatch):
    async def no_deberia(url):
        raise AssertionError("no se descarga un portal que exige sesion")

    monkeypatch.setattr(liveness, "fetch_html_with_url", no_deberia)
    r = await liveness.check_liveness("https://www.linkedin.com/jobs/view/1")
    assert r.status == "unknown"


async def _job(title, url, **extra):
    async with AsyncSessionLocal() as s:
        job = Job(source=JobSource.manual, title=title, company="Acme", description="x",
                  source_url=url, requirements=[], responsibilities=[], skills_required=[], **extra)
        s.add(job)
        await s.commit()
        await s.refresh(job)
        return job


async def test_el_script_marca_solo_las_pendientes(monkeypatch, user_and_headers):
    user, _ = user_and_headers
    cerrada = await _job("Cerrada", "https://empresa.example/1")
    abierta = await _job("Abierta", "https://empresa.example/2")
    postulada = await _job("Postulada", "https://empresa.example/3")
    async with AsyncSessionLocal() as s:
        s.add(Application(user_id=user.id, job_id=postulada.id, status=ApplicationStatus.applied))
        await s.commit()

    vistas = []

    async def fake_check(source_url, apply_url=None):
        vistas.append(source_url)
        return liveness.Liveness("closed" if source_url.endswith("/1") else "open")

    monkeypatch.setattr(script, "check_liveness", fake_check)
    monkeypatch.setattr(script, "_PAUSA_SEGUNDOS", 0)
    conteo = await script.run(limit=None)

    assert sorted(vistas) == ["https://empresa.example/1", "https://empresa.example/2"]
    assert conteo == {"closed": 1, "open": 1}
    async with AsyncSessionLocal() as s:
        assert (await s.get(Job, cerrada.id)).closed_at is not None
        a = await s.get(Job, abierta.id)
        assert a.closed_at is None and a.liveness_checked_at is not None

    # Recien comprobadas: la siguiente pasada no las vuelve a pedir.
    vistas.clear()
    await script.run(limit=None)
    assert vistas == []
