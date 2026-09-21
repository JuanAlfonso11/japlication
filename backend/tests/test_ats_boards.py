"""Ofertas leidas del ATS de cada empresa (services/ats_boards.py).

Sin red: _fetch_board se sustituye por tableros escritos a mano con la forma
real de cada API (medida en vivo contra Greenhouse, Lever y Ashby).
"""

import pytest

from app.core.config import settings
from app.services import ats_boards
from app.services.external_jobs.registry import PROVIDERS, normalize_results

_GH = [
    {
        "id": 101,
        "title": "Senior Software Engineer, Backend",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/101",
        "location": {"name": "Remote - Americas"},
        "offices": [],
        "content": "&lt;p&gt;Build APIs in Python and PostgreSQL.&lt;/p&gt;",
        "first_published": "2026-09-10T12:00:00Z",
        "application_deadline": "2099-01-31",
    },
    {
        "id": 102,
        "title": "Software Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/102",
        "location": {"name": "Hybrid - London"},
        "content": "&lt;p&gt;Office role.&lt;/p&gt;",
        "first_published": "2026-09-12T12:00:00Z",
    },
    {
        "id": 103,
        "title": "Account Executive",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/103",
        "location": {"name": "Remote"},
        "content": "Sell.",
    },
    {
        "id": 104,
        "title": "Platform Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/104",
        "location": {"name": "Home based - Americas"},
        "content": "Kubernetes.",
        "first_published": "2026-09-15T12:00:00Z",
        "application_deadline": "2001-01-01",
    },
]

_LEVER = [
    {
        "id": "abc",
        "text": "Backend Developer",
        "hostedUrl": "https://jobs.lever.co/beta/abc",
        "applyUrl": "https://jobs.lever.co/beta/abc/apply",
        "categories": {"location": "Buenos Aires", "allLocations": ["Buenos Aires"]},
        "workplaceType": "remote",
        "descriptionPlain": "Node and Go.",
        "lists": [{"text": "Requirements", "content": "<li>5 years of Go</li>"}],
        "createdAt": 1757000000000,
    }
]

_ASHBY = [
    {
        "id": "x1",
        "title": "Full Stack Engineer",
        "jobUrl": "https://jobs.ashbyhq.com/gamma/x1",
        "applyUrl": "https://jobs.ashbyhq.com/gamma/x1/application",
        "location": "Mexico City",
        "isRemote": True,
        "descriptionPlain": "React and TypeScript.",
        "publishedAt": "2026-09-01T00:00:00Z",
        "isListed": True,
    },
    {"id": "x2", "title": "Hidden Engineer", "isListed": False, "isRemote": True},
    # Medido en vivo: Ashby marca isRemote=True en ofertas hibridas.
    {"id": "x3", "title": "ML Engineer", "location": "UK - London", "isRemote": True,
     "workplaceType": "Hybrid", "isListed": True},
]


@pytest.fixture
def tableros(monkeypatch):
    empresas = [
        {"ats": "greenhouse", "slug": "acme", "name": "Acme"},
        {"ats": "lever", "slug": "beta", "name": "Beta"},
        {"ats": "ashby", "slug": "gamma", "name": "Gamma"},
    ]
    datos = {"acme": _GH, "beta": _LEVER, "gamma": _ASHBY}

    async def fake_fetch(ats, slug):
        return datos[slug]

    monkeypatch.setattr(ats_boards, "companies", lambda: empresas)
    monkeypatch.setattr(ats_boards, "_fetch_board", fake_fetch)
    monkeypatch.setattr(settings, "ATS_REMOTE_ONLY", True)
    ats_boards._results.clear()
    yield
    ats_boards._results.clear()


def test_la_lista_semilla_es_valida():
    ats_boards.companies.cache_clear()
    empresas = ats_boards.companies()
    assert len(empresas) >= 100
    assert {c["ats"] for c in empresas} == {"greenhouse", "lever", "ashby"}
    assert len({(c["ats"], c["slug"]) for c in empresas}) == len(empresas)


@pytest.mark.asyncio
async def test_greenhouse_solo_remotas_de_ingenieria(tableros):
    out = await ats_boards.search_ats_jobs("greenhouse")
    titulos = [r["title"] for r in out["results"]]
    # Hybrid-London fuera, Account Executive fuera; "Home based" cuenta como remoto.
    assert titulos == ["Platform Engineer", "Senior Software Engineer, Backend"]
    backend = out["results"][1]
    assert backend["apply_url"] == "https://boards.greenhouse.io/acme/jobs/101"
    assert backend["apply_ats"] == "greenhouse"
    assert backend["remote_type"] == "remote"
    assert "PostgreSQL" in backend["description"] and "&lt;" not in backend["description"]
    assert str(backend["deadline"]) == "2099-01-31"
    # Una fecha limite ya vencida no se guarda como si fuera futura.
    assert out["results"][0]["deadline"] is None


@pytest.mark.asyncio
async def test_filtro_de_modalidad_explicito_manda(tableros):
    out = await ats_boards.search_ats_jobs("greenhouse", remote_type_filter="hybrid")
    assert [r["title"] for r in out["results"]] == ["Software Engineer"]


@pytest.mark.asyncio
async def test_termino_de_busqueda_exige_todas_las_palabras(tableros):
    out = await ats_boards.search_ats_jobs("greenhouse", q="software engineer")
    assert [r["title"] for r in out["results"]] == ["Senior Software Engineer, Backend"]
    out = await ats_boards.search_ats_jobs("greenhouse", q="data scientist")
    assert out["results"] == []


@pytest.mark.asyncio
async def test_lever_usa_el_formulario_de_aplicar(tableros):
    out = await ats_boards.search_ats_jobs("lever")
    [job] = out["results"]
    assert job["apply_url"].endswith("/apply")
    assert job["source_url"] == "https://jobs.lever.co/beta/abc"
    assert "5 years of Go" in job["description"]
    assert job["posted_at"].year == 2025


@pytest.mark.asyncio
async def test_ashby_ignora_las_ofertas_no_listadas(tableros):
    out = await ats_boards.search_ats_jobs("ashby")
    assert [r["title"] for r in out["results"]] == ["Full Stack Engineer"]
    assert out["results"][0]["apply_url"].endswith("/application")


@pytest.mark.asyncio
async def test_un_tablero_caido_no_tumba_la_busqueda(monkeypatch):
    empresas = [
        {"ats": "greenhouse", "slug": "roto", "name": "Roto"},
        {"ats": "greenhouse", "slug": "acme", "name": "Acme"},
    ]

    async def fake_fetch(ats, slug):
        if slug == "roto":
            raise ats_boards.AtsBoardError("HTTP 500")
        return _GH

    monkeypatch.setattr(ats_boards, "companies", lambda: empresas)
    monkeypatch.setattr(ats_boards, "_fetch_board", fake_fetch)
    out = await ats_boards.search_ats_jobs("greenhouse")
    assert len(out["results"]) == 2


@pytest.mark.asyncio
async def test_si_todos_fallan_es_un_error_del_proveedor(monkeypatch):
    async def fake_fetch(ats, slug):
        raise ats_boards.AtsBoardError("HTTP 500")

    monkeypatch.setattr(ats_boards, "companies", lambda: [{"ats": "lever", "slug": "a", "name": "A"}])
    monkeypatch.setattr(ats_boards, "_fetch_board", fake_fetch)
    with pytest.raises(ats_boards.AtsBoardError):
        await ats_boards.search_ats_jobs("lever")


@pytest.mark.asyncio
async def test_registrados_y_normalizables(tableros):
    for nombre in ("greenhouse", "lever", "ashby"):
        assert nombre in PROVIDERS and PROVIDERS[nombre].no_auth
    out = await ats_boards.search_ats_jobs("ashby")
    [norm] = normalize_results(PROVIDERS["ashby"], out["results"])
    assert norm["external_id"] == "ashby:gamma:x1"
    assert PROVIDERS["ashby"].get_cached("ashby:gamma:x1")["title"] == "Full Stack Engineer"


@pytest.mark.asyncio
async def test_importar_guarda_el_formulario(async_client, user_and_headers, tableros):
    _user, headers = user_and_headers
    await ats_boards.search_ats_jobs("lever")
    response = await async_client.post(
        "/jobs/search/import",
        json={"source": "lever", "external_id": "lever:beta:abc"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["source"] == "lever"
    assert job["apply_url"] == "https://jobs.lever.co/beta/abc/apply"
    assert job["apply_ats"] == "lever"
