"""Puertas de la oferta (gates.py) y auditoria de hechos (grounding.py).

Sin base de datos ni red: corren tambien con --noconftest.
"""

from datetime import date
from types import SimpleNamespace

from app.services.apply_agent import gates, grounding


# ------------------------------------------------------------------ idioma

def test_language_required_as_a_condition():
    pedidos = gates.required_languages("We need someone fluent in German and with strong English. French is a plus.")
    assert set(pedidos) == {"german", "english"}
    assert pedidos["german"][0] == 4


def test_nice_to_have_and_mentions_are_not_requirements():
    assert gates.required_languages("German is a plus.") == {}
    assert gates.required_languages("Join our German team in Berlin.") == {}
    assert gates.required_languages("Excellent written and verbal communication skills.") == {}


def test_spanish_postings_and_spanish_profile_names():
    pedidos = gates.required_languages("Requisitos: inglés avanzado (C1). Alemán deseable.")
    assert set(pedidos) == {"english"}
    perfil = [{"name": "Inglés", "level": "Avanzado (C1)"}, {"name": "Español", "level": "Nativo"}]
    assert gates.language_gates("Requisitos: inglés avanzado (C1).", perfil) == []


def test_a_language_you_do_not_speak_blocks():
    perfil = [{"name": "English", "level": "C1"}, {"name": "Spanish", "level": "Native"}]
    [puerta] = gates.language_gates("Fluent German required.", perfil)
    assert puerta.code == "language" and puerta.level == gates.BLOCK
    assert "fluent german" in puerta.evidence[0]


def test_a_higher_level_than_declared_only_warns():
    perfil = [{"name": "English", "level": "B2"}]
    [puerta] = gates.language_gates("Native-level English required.", perfil)
    assert puerta.code == "language_level" and puerta.level == gates.WARN


def test_no_languages_in_profile_only_warns():
    [puerta] = gates.language_gates("Fluent German required.", [])
    assert puerta.level == gates.WARN


# ------------------------------------------------------------------ elegibilidad

def test_us_work_permit_blocks_someone_in_the_dominican_republic():
    puertas = gates.eligibility_gates(
        "You must be authorized to work in the United States.", "Remote - US", "DO"
    )
    assert [p.code for p in puertas] == ["work_permit"]
    assert puertas[0].level == gates.BLOCK


def test_latam_remote_passes():
    assert gates.eligibility_gates("Work from anywhere in LATAM.", "Remote - LATAM", "DO") == []


def test_clearance_blocks():
    puertas = gates.eligibility_gates("Active Secret security clearance required.", "Remote", "DO")
    assert "citizenship" in [p.code for p in puertas]


def test_closed_and_expired_jobs():
    job = SimpleNamespace(closed_at=date(2026, 1, 1), deadline=date(2026, 1, 1), description="", location="")
    codigos = [p.code for p in gates.evaluate(job, SimpleNamespace(languages=[]), "DO", today=date(2026, 2, 1))]
    assert codigos == ["closed", "deadline"]


# ------------------------------------------------------------------ hechos

PERFIL = {
    "summary": "Backend developer. Cut API latency 40% for 10,000 users.",
    "skills": [{"name": "Python"}, {"name": "PostgreSQL"}],
    "experience": [
        {"company": "Acme", "title": "Backend Developer", "start_date": "2022-03", "end_date": None,
         "bullets": ["Built APIs used by 10,000 users"]},
    ],
    "education": [{"institution": "PUCMM", "degree": "BS"}],
    "translations": {"es": {"experience": [{"title": "Desarrollador Backend"}]}},
}


def test_a_faithful_resume_passes():
    cv = {
        "summary": "Backend developer who cut API latency 40% for 10,000 users.",
        "skills": ["PostgreSQL", "Python"],
        "experience": [{"company": "Acme", "title": "Backend Developer", "start_date": "2022-03-01",
                        "end_date": None, "bullets": ["Built APIs used by 10,000 users"]}],
        "education": [{"institution": "PUCMM"}],
    }
    contenido, informe = grounding.audit_resume(cv, PERFIL)
    assert informe.ok and not informe.fixed
    assert contenido["skills"] == ["PostgreSQL", "Python"]


def test_translated_titles_are_from_the_profile():
    cv = {"experience": [{"company": "Acme", "title": "Desarrollador Backend", "start_date": "2022-03"}]}
    _, informe = grounding.audit_resume(cv, PERFIL)
    assert informe.ok


def test_invented_facts_are_reported_and_extra_skills_removed():
    cv = {
        "summary": "Backend developer with 5 years who cut latency 60%.",
        "skills": ["Python", "Kubernetes"],
        "experience": [
            {"company": "Acme", "title": "Senior Backend Developer", "start_date": "2021-01"},
            {"company": "Globex", "title": "Dev"},
        ],
        "education": [{"institution": "MIT"}],
    }
    contenido, informe = grounding.audit_resume(cv, PERFIL)
    assert contenido["skills"] == ["Python"]
    assert any("Kubernetes" in f for f in informe.fixed)
    texto = " ".join(informe.issues)
    for esperado in ("Globex", "MIT", "Senior Backend Developer", "fechas de Acme", "«5»", "«60»"):
        assert esperado in texto, esperado


def test_cover_letter_numbers():
    oferta = "Join a team of 50 people. 5 years of experience required."
    informe = grounding.audit_cover_letter(
        "Your team of 50 builds Web3 and B2B tools. I cut latency 40%. I have 5 years of experience.",
        PERFIL,
        job_text=oferta,
    )
    # "50" habla de la empresa y esta en la oferta; "5 years" es una
    # afirmacion del candidato que el perfil no respalda, aunque la oferta lo pida.
    assert informe.issues == ["La carta dice «5» y esa cifra no aparece en tu perfil."]
