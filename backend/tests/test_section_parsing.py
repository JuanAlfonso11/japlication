"""Los dos defectos que corrompian el score, y el filtro que dejaba pasar la tailnet.

Ninguno de los tres se veia desde fuera: no hay excepcion, no hay log, solo un
numero distinto del que deberia. Por eso llevan test.
"""

from app.services.job_importer import _build_skills_required, _extract_section
from app.services.skills_taxonomy import extract_skills_from_text
from app.services.url_guard import _is_public_address


OFERTA = """
Requisitos:
- 5 años de experiencia con Python
- PostgreSQL y Docker
- React
- AWS
"""


def _por_importancia(skills):
    return {
        "required": sorted(s["name"] for s in skills if s["importance"] == "required"),
        "nice_to_have": sorted(s["name"] for s in skills if s["importance"] == "nice_to_have"),
    }


def test_un_plus_de_transporte_no_convierte_lo_obligatorio_en_deseable():
    # "plus de transporte" / "plus de nocturnidad" son prestaciones normales en
    # una oferta en español. Antes partian la lista en ese punto y TODO lo que
    # venia despues -- es decir, los requisitos enteros -- pasaba a deseable.
    texto = "Plus de transporte incluido. Horario flexible.\n" + OFERTA

    resultado = _por_importancia(_build_skills_required(texto))

    assert "Python" in resultado["required"]
    assert "PostgreSQL" in resultado["required"]
    assert resultado["nice_to_have"] == []


def test_surplus_no_es_una_cabecera_de_seccion():
    # El corte se buscaba con `find`, es decir como subcadena.
    texto = "Tenemos surplus de proyectos este trimestre.\n" + OFERTA

    resultado = _por_importancia(_build_skills_required(texto))

    assert "Python" in resultado["required"]
    assert resultado["nice_to_have"] == []


def test_una_seccion_de_deseables_de_verdad_si_separa():
    # El arreglo no puede consistir en dejar de separar nunca: eso cambiaria un
    # resultado incorrecto por otro. Con una cabecera de verdad -- que es la
    # forma que este extractor entiende -- la separacion sigue funcionando.
    texto = OFERTA + "\nNice to have:\n- Kubernetes\n"

    resultado = _por_importancia(_build_skills_required(texto))

    assert "Python" in resultado["required"]
    assert "Kubernetes" in resultado["nice_to_have"]
    assert "Kubernetes" not in resultado["required"]


def test_los_requisitos_terminan_donde_termina_la_lista():
    # Las dos ramas del `if` de la linea en blanco hacian `continue`, asi que la
    # seccion no acababa nunca y se tragaba la pagina entera.
    texto = """Requirements:
- 5+ years of Python
- Experience with PostgreSQL


Sobre nosotros
Acme es una empresa fundada en 2010 con sede en Madrid.
Politica de privacidad: tratamos tus datos conforme al RGPD.
Contacto: rrhh@acme.example
"""

    recogido = _extract_section(texto, ["requirements"])

    assert recogido == ["5+ years of Python", "Experience with PostgreSQL"]


def test_una_linea_en_blanco_suelta_no_corta_la_lista():
    # Es lo que decia el comentario y el codigo no hacia: las listas llevan
    # huecos de uno, y cortar en el primero perderia requisitos de verdad.
    texto = """Requirements:
- Python

- PostgreSQL
"""

    assert _extract_section(texto, ["requirements"]) == ["Python", "PostgreSQL"]


def test_las_siglas_de_dos_letras_no_inventan_habilidades():
    # Este mismo escaner corre sobre el CV subido, asi que un falso positivo
    # aqui acaba escrito en el borrador del perfil del usuario.
    assert extract_skills_from_text("El equipo de TS revisa los tickets.") == []
    assert extract_skills_from_text("Reunion el proximo dl por la tarde.") == []
    # Y la forma larga, que es como lo escriben las ofertas, se sigue detectando.
    assert "Machine Learning" in extract_skills_from_text("Buscamos alguien de machine learning.")


def test_el_rango_de_tailscale_no_cuenta_como_publico():
    # 100.64.0.0/10 no es private, ni loopback, ni link-local, ni reserved, asi
    # que la lista de negaciones anterior lo dejaba pasar entero -- y es
    # exactamente el rango de la tailnet del usuario.
    assert _is_public_address("100.64.1.1") is False
    assert _is_public_address("100.100.100.100") is False
    assert _is_public_address("::ffff:100.64.1.1") is False
    # Lo que si es publico lo sigue siendo.
    assert _is_public_address("8.8.8.8") is True
