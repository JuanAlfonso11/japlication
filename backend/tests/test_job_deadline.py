"""La fecha límite: solo cuando la oferta la declara, nunca adivinada.

El riesgo aquí no es perder una fecha, es inventarla. Una oferta está llena de
fechas —cuándo se fundó la empresa, desde cuándo existe el equipo, la fecha de
publicación— y un aviso de "te quedan 2 días" basado en una de ellas hace que
dejes de fiarte de todos los avisos. Por eso la mitad de estos tests comprueban
que NO extrae nada.
"""

from datetime import date, timedelta

from app.services.job_importer import _extract_deadline, parse_jobposting_jsonld

FUTURO = date.today() + timedelta(days=45)


def test_validthrough_del_json_ld_es_la_fuente_preferida():
    # Es el campo que schema.org define para esto: cuando la pagina lo trae no
    # hay nada que adivinar.
    item = {
        "title": "Ingeniero backend",
        "hiringOrganization": {"name": "Acme"},
        "description": "Buscamos alguien con Python.",
        "validThrough": f"{FUTURO.isoformat()}T23:59:59Z",
    }

    assert parse_jobposting_jsonld(item)["deadline"] == FUTURO


def test_se_extrae_del_texto_cuando_no_hay_validthrough():
    texto = f"Fecha límite: {FUTURO.strftime('%d/%m/%Y')}. Envía tu CV."

    assert _extract_deadline(texto) == FUTURO


def test_formato_largo_en_espanol():
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    texto = f"Postula antes del {FUTURO.day} de {meses[FUTURO.month - 1]} de {FUTURO.year}."

    assert _extract_deadline(texto) == FUTURO


def test_formato_en_ingles():
    texto = f"Application deadline: {FUTURO.strftime('%B %d, %Y')}"

    assert _extract_deadline(texto) == FUTURO


def test_una_fecha_sin_marcador_no_es_una_fecha_limite():
    # Este es el test que importa. Acme se fundó en 2010 y el equipo existe
    # desde una fecha concreta; ninguna de las dos es un plazo.
    texto = (
        f"Acme se fundó en 2010. El equipo de datos existe desde el "
        f"{FUTURO.strftime('%d/%m/%Y')} y sigue creciendo."
    )

    assert _extract_deadline(texto) is None


def test_prisa_sin_fecha_no_es_una_fecha():
    assert _extract_deadline("Fecha límite: aplica pronto, plazas limitadas.") is None


def test_una_fecha_limite_ya_vencida_se_descarta():
    # Casi siempre es otra cosa mal leída, y avisar de un plazo vencido no
    # ayuda a nadie.
    pasado = date.today() - timedelta(days=30)
    texto = f"Fecha límite: {pasado.strftime('%d/%m/%Y')}"

    assert _extract_deadline(texto) is None


def test_una_oferta_que_no_dice_nada_no_tiene_plazo():
    item = {
        "title": "Ingeniero backend",
        "hiringOrganization": {"name": "Acme"},
        "description": "Buscamos alguien con Python y PostgreSQL.",
    }

    assert parse_jobposting_jsonld(item)["deadline"] is None
