"""Lo que se le pide a los portales.

El fallo que cierra este archivo no daba error en ninguna parte: diez de las
doce fuentes gratuitas devolvían cero resultados y reportaban OK, porque se
les mandaba el titular del perfil entero como consulta. Medido contra las 12
en el mismo instante: 25 resultados con el titular, 276 con "Software
Engineer". Un resultado silenciosamente vacío es peor que un error.
"""

from types import SimpleNamespace

from app.api.v1.routers.jobs import (
    _clean_search_term,
    _profile_search_query,
    _profile_search_terms,
)


def _perfil(headline="", experience=None, skills=None):
    return SimpleNamespace(
        headline=headline, experience=experience or [], skills=skills or []
    )


TITULAR_REAL = "Computer Science Engineer | Software Engineer | Backend, Full-Stack & Applied AI"


def test_el_titular_real_se_parte_en_terminos_buscables():
    terms = _profile_search_terms(_perfil(headline=TITULAR_REAL))

    # Ninguno puede seguir siendo la frase entera: eso es lo que devolvia cero.
    assert all(len(t.split()) <= 4 for t in terms), terms
    assert TITULAR_REAL not in terms
    assert "Software Engineer" in terms
    # Y se conservan los otros puestos que el titular nombra, en vez de tirarlos.
    assert len(terms) >= 3


def test_el_primer_termino_es_el_que_usa_quien_solo_quiere_uno():
    assert _profile_search_query(_perfil(headline=TITULAR_REAL)) == "Computer Science Engineer"


def test_las_palabras_de_adorno_no_estrechan_la_busqueda():
    # Ninguna oferta se titula "Senior Aspiring Backend Engineer".
    assert _clean_search_term("Senior Aspiring Backend Engineer") == "Backend Engineer"


def test_una_frase_larga_se_recorta_en_vez_de_mandarse_entera():
    largo = "Backend Engineer specialising in distributed systems and event driven design"

    assert len((_clean_search_term(largo) or "").split()) <= 4


def test_sin_titular_se_cae_al_puesto_mas_reciente():
    terms = _profile_search_terms(
        _perfil(experience=[{"title": "Data Engineer"}, {"title": "Analyst"}])
    )

    assert terms[0] == "Data Engineer"


def test_sin_titular_ni_experiencia_se_usan_las_habilidades():
    terms = _profile_search_terms(_perfil(skills=[{"name": "Python"}, {"name": "Docker"}]))

    assert "Python" in terms


def test_un_perfil_vacio_no_produce_consulta():
    assert _profile_search_terms(_perfil()) == []
    assert _profile_search_query(_perfil()) is None


def test_no_se_repiten_terminos_equivalentes():
    terms = _profile_search_terms(
        _perfil(headline="Backend Engineer | backend engineer", experience=[{"title": "Backend Engineer"}])
    )

    assert len(terms) == 1
