"""La parte del SSRF que no tenia ni una sola asercion: las redirecciones.

test_url_guard.py prueba a fondo `validate_public_http_url` en aislamiento,
pero el bypass real nunca fue el primer salto — es el segundo. Una pagina
publica responde `302 Location: http://169.254.169.254/` y, si alguien
cambiara `follow_redirects=False` por `True` "para simplificar", httpx
seguiria el salto sin volver a validar nada y el agujero se reabriria sin que
fallara ni un test.

Tambien cubre el tope de descarga, que se comprobaba DESPUES de bufferizar el
cuerpo entero: una respuesta chunked (sin Content-Length) de cualquier tamano
tumbaba el contenedor por memoria antes de llegar al chequeo.
"""

import httpx
import pytest

from app.services import job_importer
from app.services.job_importer import MAX_DOWNLOAD_BYTES, JobImportError, fetch_html

PUBLIC = "https://example.com/careers/1"


def _client_factory(monkeypatch, handler):
    """Hace que fetch_html use un transporte falso, sin tocar la red."""
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(job_importer.httpx, "AsyncClient", factory)


@pytest.fixture(autouse=True)
def _allow_public_urls(monkeypatch):
    """El guard resuelve DNS de verdad; aqui solo interesa el bucle de saltos.

    Deja pasar los hosts publicos del test y rechaza los internos, que es
    exactamente el contrato que validate_public_http_url cumple en produccion.
    """
    blocked = ("localhost", "127.0.0.1", "169.254.169.254", "db", "10.", "192.168.")

    def fake_validate(url: str) -> str:
        host = httpx.URL(url).host or ""
        if any(host.startswith(b) or host == b for b in blocked):
            raise job_importer.UnsafeUrlError(f"La URL apunta a una direccion interna: {host}")
        return url

    monkeypatch.setattr(job_importer, "validate_public_http_url", fake_validate)


@pytest.mark.asyncio
async def test_redirect_to_internal_address_is_refused(monkeypatch):
    """El caso que importa: pagina publica -> 302 a la metadata de la nube."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        raise AssertionError(f"no se debio pedir {request.url}")

    _client_factory(monkeypatch, handler)

    with pytest.raises(JobImportError) as exc:
        await fetch_html(PUBLIC)
    assert "interna" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_relative_redirect_is_resolved_and_revalidated(monkeypatch):
    """Una Location relativa es normal y debe seguirse, no rechazarse."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/careers/1":
            return httpx.Response(302, headers={"location": "/careers/final"})
        return httpx.Response(200, html="<html><body>ok</body></html>")

    _client_factory(monkeypatch, handler)
    assert "ok" in await fetch_html(PUBLIC)


@pytest.mark.asyncio
async def test_redirect_loop_gives_up(monkeypatch):
    """Sin tope, una cadena circular corre para siempre."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://example.com/careers/next"})

    _client_factory(monkeypatch, handler)

    with pytest.raises(JobImportError) as exc:
        await fetch_html(PUBLIC)
    assert "redirecciones" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_oversized_chunked_body_is_cut_off(monkeypatch):
    """Sin Content-Length que delate el tamano, el corte tiene que ocurrir
    mientras se lee. Se emiten mas bytes del tope: si el codigo volviera a
    bufferizar primero, este test tardaria y pasaria igual — por eso tambien
    se comprueba cuanto se llego a leer."""
    emitted = {"bytes": 0}
    chunk = b"x" * (256 * 1024)

    def handler(request: httpx.Request) -> httpx.Response:
        # Generador ASINCRONO: un AsyncClient exige un AsyncByteStream, y con
        # uno sincrono httpx ni siquiera llega a leer el cuerpo.
        async def stream():
            # Suficiente para pasarse del tope tres veces.
            for _ in range((MAX_DOWNLOAD_BYTES // len(chunk)) * 3):
                emitted["bytes"] += len(chunk)
                yield chunk

        return httpx.Response(200, content=stream())

    _client_factory(monkeypatch, handler)

    with pytest.raises(JobImportError) as exc:
        await fetch_html(PUBLIC)
    assert "grande" in str(exc.value).lower()
    # Se corto cerca del tope, no despues de tragarse el cuerpo entero.
    assert emitted["bytes"] < MAX_DOWNLOAD_BYTES * 2


@pytest.mark.asyncio
async def test_declared_content_length_over_the_cap_is_refused(monkeypatch):
    """El camino barato: el servidor dice honestamente que es enorme."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": str(MAX_DOWNLOAD_BYTES + 1)},
            content=b"x" * 10,
        )

    _client_factory(monkeypatch, handler)

    with pytest.raises(JobImportError):
        await fetch_html(PUBLIC)
