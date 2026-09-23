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
