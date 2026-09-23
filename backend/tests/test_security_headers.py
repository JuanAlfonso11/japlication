import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/app/android-update", "/auth/me"])
async def test_security_headers_on_success_and_error(async_client, path):
    # /auth/me without a token is a 401: error responses need them too.
    response = await async_client.get(path)
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Strict-Transport-Security"].startswith("max-age=")


async def test_api_docs_hidden_by_default(async_client):
    # async_client's base_url carries the /api/v1 prefix; the docs live at the root.
    for path in ("/docs", "/redoc", "/openapi.json"):
        response = await async_client.get(f"http://test{path}")
        assert response.status_code == 404, path
