"""Encontrar el formulario detrás del listado.

Lo que más importa aquí no es acertar, es no inventar. Un destino equivocado
manda la candidatura a ningún sitio y parece enviada; un correo equivocado la
manda al buzón de privacidad de la empresa. Por eso la mitad de estos casos
comprueban que NO resuelve nada.
"""

import pytest

from app.services import apply_target
from app.services.apply_target import (
    ApplyTarget,
    apply_email_in_text,
    detect_ats,
    resolve_apply_target,
)


def _fake_fetch(html: str, final_url: str):
    async def _fetch(url: str):
        return html, final_url
    return _fetch


@pytest.fixture
def sin_dns(monkeypatch):
    """Deja pasar la validación de URL, salvo lo que es de verdad interno.

    Los primeros tests dependían de que el DNS resolviera `acme.com` y
    `acortador.example` dentro del contenedor, así que medían la red además de
    lo que decían medir — y `.example` no resuelve nunca, por diseño. url_guard
    tiene su propia batería; aquí lo que se prueba es el resolver.

    El bloqueo de lo interno se conserva de verdad (no se sustituye por un
    `lambda: True`), porque hay un test que comprueba justo eso.
    """
    real = apply_target.validate_public_http_url

    def _permisivo(url: str) -> str:
        if "127.0.0.1" in url or "localhost" in url or "://100." in url:
            return real(url)
        return url

    monkeypatch.setattr(apply_target, "validate_public_http_url", _permisivo)


# --- detectar el ATS por el host ------------------------------------------

def test_reconoce_los_ats_por_su_host():
    assert detect_ats("https://boards.greenhouse.io/acme/jobs/123") == "greenhouse"
    assert detect_ats("https://jobs.lever.co/acme/abc-123") == "lever"
    assert detect_ats("https://jobs.ashbyhq.com/acme/xyz") == "ashby"
    assert detect_ats("https://acme.myworkdayjobs.com/es/acme/job/1") == "workday"
    assert detect_ats("https://apply.workable.com/acme/j/ABC/") == "workable"


def test_un_portal_no_es_un_ats():
    # Aterrizar en el listado no es haber encontrado el formulario.
    assert detect_ats("https://jobicy.com/jobs/153109-senior-engineer") is None
    assert detect_ats("https://remotejobs.org/remote-jobs/backend") is None
    assert detect_ats(None) is None


# --- el correo de postulación ---------------------------------------------

def test_encuentra_el_correo_cuando_la_oferta_lo_pide():
    texto = "Para postular, envía tu CV a talento@acme.com antes del viernes."

    assert apply_email_in_text(texto) == "talento@acme.com"


def test_encuentra_el_correo_en_ingles():
    assert apply_email_in_text("Send your resume to jobs@acme.io") == "jobs@acme.io"


def test_un_correo_suelto_no_es_para_postular():
    # El caso que importa: mandar la candidatura al buzón equivocado es peor
    # que no mandarla, porque parece enviada y no llega a nadie.
    texto = "Acme S.A. Política de privacidad: escribe a privacy@acme.com."

    assert apply_email_in_text(texto) is None


def test_los_buzones_genericos_se_descartan_aunque_esten_cerca_del_marcador():
    texto = "Send your CV to no-reply@acme.com if you have questions."

    assert apply_email_in_text(texto) is None


def test_sin_texto_no_hay_correo():
    assert apply_email_in_text("") is None


# --- resolver el destino ---------------------------------------------------

@pytest.mark.asyncio
async def test_sigue_el_listado_hasta_el_formulario(monkeypatch, sin_dns):
    html = """
    <html><body>
      <h1>Senior Backend Engineer</h1>
      <a href="https://jobicy.com/companies/acme">Ver empresa</a>
      <a href="https://boards.greenhouse.io/acme/jobs/4567">Apply now</a>
    </body></html>
    """
    monkeypatch.setattr(
        apply_target, "fetch_html_with_url",
        _fake_fetch(html, "https://remotejobs.org/remote-jobs/senior-engineer"),
    )

    target = await resolve_apply_target("https://remotejobs.org/remote-jobs/senior-engineer")

    assert target.url == "https://boards.greenhouse.io/acme/jobs/4567"
    assert target.ats == "greenhouse"
    assert target.note is None


@pytest.mark.asyncio
async def test_el_enlace_al_ats_gana_al_boton_generico(monkeypatch, sin_dns):
    # El botón "Apply" del portal suele llevar a otra página del portal. El
    # enlace que ya apunta a un ATS es el destino de verdad.
    html = """
    <html><body>
      <a href="/apply-now">Apply</a>
      <a href="https://jobs.lever.co/acme/abc-123">Ver oferta original</a>
    </body></html>
    """
    monkeypatch.setattr(
        apply_target, "fetch_html_with_url",
        _fake_fetch(html, "https://remotejobs.org/remote-jobs/backend"),
    )

    target = await resolve_apply_target("https://remotejobs.org/remote-jobs/backend")

    assert target.ats == "lever"
    assert target.url == "https://jobs.lever.co/acme/abc-123"


@pytest.mark.asyncio
async def test_la_pagina_propia_de_la_empresa_tambien_vale(monkeypatch, sin_dns):
    # No todas las empresas usan un ATS conocido, y su propia página de empleo
    # sigue siendo mejor destino que quedarse en el listado.
    html = '<html><body><a href="https://acme.com/careers/backend">Postular</a></body></html>'
    monkeypatch.setattr(
        apply_target, "fetch_html_with_url",
        _fake_fetch(html, "https://remotejobs.org/remote-jobs/backend-1"),
    )

    target = await resolve_apply_target("https://remotejobs.org/remote-jobs/backend-1")

    assert target.url == "https://acme.com/careers/backend"
    assert target.ats is None


@pytest.mark.asyncio
async def test_si_la_redireccion_ya_aterrizo_en_el_ats_no_hace_falta_buscar(monkeypatch, sin_dns):
    monkeypatch.setattr(
        apply_target, "fetch_html_with_url",
        _fake_fetch("<html></html>", "https://jobs.ashbyhq.com/acme/xyz"),
    )

    target = await resolve_apply_target("https://remotejobs.org/remote-jobs/backend-1")

    assert target.ats == "ashby"
    assert target.url == "https://jobs.ashbyhq.com/acme/xyz"


@pytest.mark.asyncio
async def test_sin_enlace_de_postular_lo_dice_en_vez_de_inventar(monkeypatch, sin_dns):
    html = "<html><body><p>Una oferta sin ningún enlace.</p></body></html>"
    monkeypatch.setattr(
        apply_target, "fetch_html_with_url",
        _fake_fetch(html, "https://remotejobs.org/remote-jobs/backend-1"),
    )

    target = await resolve_apply_target("https://remotejobs.org/remote-jobs/backend-1")

    assert target.url is None
    assert target.ats is None
    assert target.note is not None


@pytest.mark.asyncio
async def test_un_listado_que_no_abre_no_tumba_nada(monkeypatch, sin_dns):
    async def _boom(url):
        raise RuntimeError("la red se cayó")
    monkeypatch.setattr(apply_target, "fetch_html_with_url", _boom)

    target = await resolve_apply_target("https://remotejobs.org/remote-jobs/backend-1")

    assert isinstance(target, ApplyTarget)
    assert target.url is None
    assert target.note is not None


@pytest.mark.asyncio
async def test_una_url_interna_se_rechaza_antes_de_pedirla(monkeypatch):
    # url_guard ya cubre esto, pero el resolver no puede ser la puerta por la
    # que se cuele: si validara después de descargar, ya sería tarde.
    llamado = False

    async def _no_deberia(url):
        nonlocal llamado
        llamado = True
        return "", url

    monkeypatch.setattr(apply_target, "fetch_html_with_url", _no_deberia)

    target = await resolve_apply_target("http://127.0.0.1:8446/app.apk")

    assert llamado is False
    assert target.url is None


@pytest.mark.asyncio
async def test_el_correo_de_la_descripcion_sobrevive_aunque_no_haya_formulario(monkeypatch, sin_dns):
    html = "<html><body><p>Nada que enlazar.</p></body></html>"
    monkeypatch.setattr(
        apply_target, "fetch_html_with_url",
        _fake_fetch(html, "https://remotejobs.org/remote-jobs/backend-1"),
    )

    target = await resolve_apply_target(
        "https://remotejobs.org/remote-jobs/backend-1",
        description="Postula enviando tu CV a talento@acme.com",
    )

    assert target.email == "talento@acme.com"
    assert target.url is None


@pytest.mark.asyncio
async def test_un_portal_que_exige_cuenta_lo_dice_con_su_nombre(monkeypatch, sin_dns):
    # Comprobado contra jobicy: su botón "Apply Now" pasa por su propio
    # registro y su API v2 no trae la URL del empleador. Eso es un muro, no un
    # hueco que se pueda mejorar, y confundir los dos hace perder el tiempo.
    monkeypatch.setattr(
        apply_target, "fetch_html_with_url",
        _fake_fetch("<html><body><p>nada</p></body></html>", "https://jobicy.com/jobs/1"),
    )

    target = await resolve_apply_target("https://jobicy.com/jobs/1")

    assert target.url is None
    assert "cuenta" in (target.note or "")
    assert "Jobicy" in (target.note or "")


@pytest.mark.asyncio
async def test_no_se_pide_la_pagina_de_un_portal_que_ya_se_sabe_cerrado(monkeypatch, sin_dns):
    # Pedirla igual sería una petición a un tercero a cambio de nada, y son
    # 43 de sus 70 vacantes.
    pedida = False

    async def _no_deberia(url):
        nonlocal pedida
        pedida = True
        return "", url

    monkeypatch.setattr(apply_target, "fetch_html_with_url", _no_deberia)

    target = await resolve_apply_target("https://do.linkedin.com/jobs/view/algo-123")

    assert pedida is False
    assert "LinkedIn" in (target.note or "")
