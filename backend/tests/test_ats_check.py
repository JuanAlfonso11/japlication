"""El chequeo tiene que DETECTAR un PDF roto, no solo aprobar uno bueno.

Una aserción que no puede fallar no prueba nada (L-002), y aquí es fácil
escribir una: casi cualquier PDF real pasa los siete chequeos. Por eso cada
caso rompe algo a propósito y comprueba que el veredicto cambia.
"""

import io

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from app.services.ats_check import check_resume_pdf
from app.services.resume_pdf import render_resume_pdf

CONTENT = {
    "summary": "Ingeniero backend con ocho años construyendo servicios en Python.",
    "skills": ["Python", "PostgreSQL", "Docker", "FastAPI"],
    "experience": [
        {
            "company": "Acme",
            "title": "Ingeniero backend senior",
            "start_date": "2020-01",
            "end_date": None,
            "achievements": ["Migró el pipeline de ingesta a colas asíncronas."],
        }
    ],
    "education": [
        {"institution": "Universidad de Chile", "degree": "Ingeniería", "field": "Informática"}
    ],
}


def _render(content=None, **kwargs):
    return render_resume_pdf(
        full_name=kwargs.pop("full_name", "Juan Alfonso Alvarado"),
        contact_info={"city": "Santiago", "country": "Chile", "phone": "+56 9 1234 5678"},
        content=CONTENT if content is None else content,
        language="es",
        email=kwargs.pop("email", "juan@example.com"),
    )


def _check(pdf, **kwargs):
    return check_resume_pdf(
        pdf,
        full_name=kwargs.pop("full_name", "Juan Alfonso Alvarado"),
        email=kwargs.pop("email", "juan@example.com"),
        content=kwargs.pop("content", CONTENT),
        language="es",
    )


def _codes(report):
    return {f.code for f in report.findings}


def test_el_pdf_que_genera_jobpilot_pasa():
    # El caso base. Si esto falla, el generador dejo de ser legible para un ATS
    # y el resto de los tests no significan nada.
    report = _check(_render())

    assert report.readable is True
    assert report.pages == 1
    assert report.extracted_chars > 200
    assert [f for f in report.findings if f.level == "error"] == []
    assert sorted(report.keywords_found) == ["Docker", "FastAPI", "PostgreSQL", "Python"]
    assert report.keywords_missing == []


def test_un_pdf_sin_capa_de_texto_se_detecta():
    # Un PDF de una sola imagen: se ve perfecto al abrirlo y para un ATS esta
    # en blanco. Es el fallo que ningun humano puede ver revisando el archivo.
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    c.rect(100, 100, 200, 200, fill=1)  # solo un rectangulo, cero texto
    c.showPage()
    c.save()

    report = _check(buffer.getvalue())

    assert report.readable is False
    assert "no_text_layer" in _codes(report)


def test_un_archivo_que_no_es_un_pdf_se_reporta_en_vez_de_reventar():
    report = _check(b"esto no es un PDF")

    assert report.readable is False
    assert "unreadable" in _codes(report)


def test_si_falta_el_correo_es_un_error_no_un_aviso():
    # El correo es la clave con la que el ATS crea la ficha del candidato.
    # Se renderiza sin el y se comprueba pidiendo que este.
    pdf = _render(email=None)

    report = _check(pdf, email="juan@example.com")

    assert report.readable is False
    assert "email_missing" in _codes(report)


def test_si_falta_el_nombre_se_dice_que_parte_falta():
    pdf = _render(full_name="Juan Alvarado")

    report = _check(pdf, full_name="Juan Alfonso Alvarado")

    assert report.readable is False
    assert "name_missing" in _codes(report)
    mensaje = next(f.message for f in report.findings if f.code == "name_missing")
    assert "Alfonso" in mensaje


def test_una_habilidad_que_no_llego_al_pdf_se_reporta():
    # El caso real: resume_adapter pone una habilidad para esta vacante y el
    # renderizado la pierde. Es justo la palabra por la que filtran.
    pdf = _render()
    content_con_extra = {**CONTENT, "skills": CONTENT["skills"] + ["Kubernetes"]}

    report = _check(pdf, content=content_con_extra)

    assert "keywords_missing" in _codes(report)
    assert report.keywords_missing == ["Kubernetes"]
    # Sigue siendo enviable: falta una palabra, no esta roto.
    assert report.readable is True


def test_el_texto_pegado_se_detecta():
    # Sin espacios entre palabras: el PDF se ve bien y el ATS lee una sola
    # cadena. Se construye a mano porque reportlab no produce esto solo.
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    y = 750
    for _ in range(25):
        c.drawString(40, y, "JuanAlfonsoAlvaradoIngenieroBackendSeniorPythonPostgreSQLDockerFastAPI")
        y -= 14
    c.showPage()
    c.save()

    report = _check(buffer.getvalue())

    assert report.readable is False
    assert "text_glued" in _codes(report)
