"""El cliente HTTP compartido de los conectores: reintento y circuit breaker.

Antes cada conector abria su propio httpx.AsyncClient con el timeout escrito a
mano y sin reintentar nada, asi que un corte de un segundo borraba esa fuente
de los resultados y una fuente caida se martillaba a pleno ritmo en cada
busqueda, pagando el timeout completo cada vez.
"""

import httpx
import pytest

from app.services.external_jobs import http as external_http


@pytest.fixture(autouse=True)
def _reset_breaker():
    """Estado de proceso: sin esto un test contamina al siguiente."""
    external_http._breaker.__init__()  # noqa: SLF001
    yield
    external_http._breaker.__init__()  # noqa: SLF001


def _transport(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(external_http.httpx, "AsyncClient", factory)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """El backoff es real; en los tests no hace falta esperarlo."""
    async def instant(_seconds):
        return None

    monkeypatch.setattr(external_http.asyncio, "sleep", instant)


@pytest.mark.asyncio
async def test_transient_500_is_retried_and_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500)
        return httpx.Response(200, json={"ok": True})

    _transport(monkeypatch, handler)
    resp = await external_http.get("demo", "https://example.com/jobs")

    assert resp.status_code == 200
    assert calls["n"] == 2, "debio reintentar exactamente una vez"


@pytest.mark.asyncio
async def test_a_404_is_not_retried(monkeypatch):
    """Una peticion mal formada repetida sigue mal formada: reintentarla solo
    gasta tiempo del plazo del agregado."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404)

    _transport(monkeypatch, handler)
    resp = await external_http.get("demo", "https://example.com/jobs")

    assert resp.status_code == 404
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_a_404_does_not_open_the_circuit(monkeypatch):
    """El proveedor respondio: esta vivo. Solo cuentan los fallos de transporte
    y los 5xx."""
    def handler(request):
        return httpx.Response(404)

    _transport(monkeypatch, handler)
    for _ in range(5):
        await external_http.get("demo", "https://example.com/jobs")

    assert not external_http.is_circuit_open("demo")


@pytest.mark.asyncio
async def test_circuit_opens_after_repeated_failures_and_then_skips(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectError("boom", request=request)

    _transport(monkeypatch, handler)

    for _ in range(external_http._BREAKER_THRESHOLD):  # noqa: SLF001
        with pytest.raises(httpx.ConnectError):
            await external_http.get("demo", "https://example.com/jobs", retries=0)

    assert external_http.is_circuit_open("demo")
    antes = calls["n"]

    # Con el circuito abierto ya ni se intenta: ese es el punto, no pagar el
    # timeout de una fuente que se sabe caida.
    with pytest.raises(external_http.ProviderUnavailable):
        await external_http.get("demo", "https://example.com/jobs")
    assert calls["n"] == antes, "no debio tocar la red"


@pytest.mark.asyncio
async def test_a_success_closes_the_circuit(monkeypatch):
    state = {"fail": True}

    def handler(request):
        if state["fail"]:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={})

    _transport(monkeypatch, handler)

    for _ in range(external_http._BREAKER_THRESHOLD - 1):  # noqa: SLF001
        with pytest.raises(httpx.ConnectError):
            await external_http.get("demo", "https://example.com/jobs", retries=0)
    assert not external_http.is_circuit_open("demo")

    state["fail"] = False
    await external_http.get("demo", "https://example.com/jobs")

    # El contador se reinicia: un fallo aislado no debe acumularse para
    # siempre hasta abrir el circuito de una fuente que funciona.
    assert external_http.open_circuits() == {}


@pytest.mark.asyncio
async def test_one_provider_failing_does_not_affect_another(monkeypatch):
    def handler(request):
        if "bad" in str(request.url):
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={})

    _transport(monkeypatch, handler)

    for _ in range(external_http._BREAKER_THRESHOLD):  # noqa: SLF001
        with pytest.raises(httpx.ConnectError):
            await external_http.get("malo", "https://bad.example.com/x", retries=0)

    assert external_http.is_circuit_open("malo")
    assert not external_http.is_circuit_open("bueno")
    assert (await external_http.get("bueno", "https://ok.example.com/x")).status_code == 200


@pytest.mark.asyncio
async def test_timeout_comes_from_settings(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "EXTERNAL_JOBS_TIMEOUT_SECONDS", 3.5)
    assert external_http.timeout_seconds() == 3.5
