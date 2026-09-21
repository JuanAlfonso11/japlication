"""Ofertas que exigen permiso de trabajo en un pais (services/work_authorization.py).

Los casos salen de ofertas reales del escaner de ATS: "Remote - United
States", "Home based - Americas", "must be eligible to work in the U.S.".
"""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.db.session import AsyncSessionLocal
from app.models.career_profile import CareerProfile
from app.models.enums import JobSource
from app.models.job import Job
from app.models.job_match import JobMatch
from app.services.match_engine import WORK_AUTH_SCORE_CAP, compute_match
from app.services.work_authorization import country_code, detect, profile_country


@pytest.mark.parametrize(
    "description, location, regions, explicit, no_sponsor",
    [
        ("You must be authorized to work in the United States.", "Remote", ("US",), True, False),
        ("Applicants must be eligible to work in the U.S. without sponsorship.", "Remote", ("US",), True, True),
        ("Candidates must reside in Canada or the U.S.", "Remote", ("CA", "US"), True, False),
        ("US citizenship required due to security clearance.", "Remote", ("US",), True, False),
        ("USA only.", "Remote", ("US",), True, False),
        ("This role is open to candidates in LATAM.", "Remote", ("LATAM",), True, False),
        ("Join us! Great team.", "Remote - US", ("US",), False, False),
        ("We are unable to sponsor visas.", "Remote - US", ("US",), False, True),
        ("Join us!", "Remote - Americas", ("AMERICAS",), False, False),
        ("Hybrid", "UK - London · Hybrid", ("UK",), False, False),
    ],
)
def test_detecta_la_restriccion(description, location, regions, explicit, no_sponsor):
    wa = detect(description, location)
    assert wa.regions == regions
    assert wa.explicit is explicit
    assert wa.no_sponsorship is no_sponsor


@pytest.mark.parametrize(
    "description, location",
    [
        ("Join us and help us build the future.", "Remote"),
        ("Join us!", "Anywhere in the world"),
        # Horario, no permiso de trabajo.
        ("Must be located in a US time zone.", "Remote"),
        ("We offer visa sponsorship and relocation.", "Worldwide"),
        ("Our team is distributed across Europe and the US.", "Remote"),
    ],
)
def test_no_inventa_restricciones(description, location):
    assert not detect(description, location).restricted


def test_quien_queda_fuera():
    assert detect("", "Remote - US").blocks("DO") is True
    assert detect("", "Remote - Americas").blocks("DO") is False
    assert detect("", "Remote - LATAM").blocks("DO") is False
    assert detect("", "Remote - EMEA").blocks("DO") is True
    assert detect("", "Remote - US").blocks("US") is False
    # Sin pais en el perfil, o sin pais en la oferta: no se sabe.
    assert detect("", "Remote - US").blocks(None) is None
    assert detect("We cannot sponsor visas.", "Remote").blocks("DO") is None


def test_pais_del_perfil():
    assert country_code("República Dominicana") == "DO"
    assert country_code("Santo Domingo") == "DO"
    assert country_code("Mexico") == "MX"
    # "Santiago" solo es Chile si no es Santiago de los Caballeros.
    assert detect("", "Santiago de los Caballeros, Dominican Republic").regions == ("DO",)
    assert detect("", "Santiago, Chile").regions == ("CL",)
    assert country_code("") is None
    perfil = SimpleNamespace(contact_info={"city": "Santo Domingo", "country": "República Dominicana"})
    assert profile_country(perfil) == "DO"


def test_el_match_topa_la_puntuacion_y_lo_explica():
    perfil = SimpleNamespace(
        headline="Backend Engineer",
        summary="Python",
        skills=[{"name": "Python"}],
        experience=[],
        education=[],
        contact_info={"country": "República Dominicana"},
    )
    job = SimpleNamespace(
        title="Python Engineer",
        company="Acme",
        description="Python. Must be authorized to work in the United States.",
        location="Remote",
        seniority=None,
        requirements=[],
        skills_required=[{"name": "Python", "importance": "required"}],
    )
    result = compute_match(perfil, job, use_llm=False)
    assert result["overall_score"] <= WORK_AUTH_SCORE_CAP
    assert "EE. UU." in result["concerns"][0]
    assert "República Dominicana" in result["concerns"][0]

    # La misma oferta, sin restriccion: sin tope.
    job.description = "Python."
    assert compute_match(perfil, job, use_llm=False)["overall_score"] > WORK_AUTH_SCORE_CAP


async def _job(title, **extra):
    async with AsyncSessionLocal() as s:
        job = Job(source=JobSource.manual, title=title, company="Acme", description="Build things.",
                  requirements=[], responsibilities=[], skills_required=[], **extra)
        s.add(job)
        await s.commit()
        await s.refresh(job)
        return job


async def test_la_cola_quita_cerradas_y_vencidas_y_marca_el_bloqueo(async_client, user_and_headers):
    from datetime import datetime, timezone

    user, headers = user_and_headers
    abierta = await _job("Abierta", location="Remote - US")
    cerrada = await _job("Cerrada", closed_at=datetime.now(timezone.utc))
    vencida = await _job("Vencida", deadline=date.today() - timedelta(days=1))
    async with AsyncSessionLocal() as s:
        s.add(CareerProfile(user_id=user.id, contact_info={"country": "República Dominicana"}))
        for j in (abierta, cerrada, vencida):
            s.add(JobMatch(user_id=user.id, job_id=j.id, overall_score=50, matched_skills=[],
                           missing_skills=[], concerns=[]))
        await s.commit()

    resp = await async_client.get("/matches", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [j["title"] for j in body["items"]] == ["Abierta"]
    assert body["total"] == 1
    wa = body["items"][0]["work_auth"]
    assert wa["regions"] == ["US"] and wa["blocks_you"] is True
