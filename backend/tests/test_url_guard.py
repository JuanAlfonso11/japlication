import pytest

from app.services.url_guard import UnsafeUrlError, validate_public_http_url


def test_allows_a_normal_public_job_posting():
    url = "https://boards.greenhouse.io/acme/jobs/42"
    assert validate_public_http_url(url) == url


def test_allows_http_as_well_as_https():
    assert validate_public_http_url("http://example.com/jobs/1")


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000/api/v1/auth/me",
        "http://127.0.0.1/",
        "http://127.0.0.1:5432/",
        "http://[::1]/",
        "http://0.0.0.0/",
    ],
)
def test_blocks_loopback(url):
    """The backend must not be usable as a proxy onto itself."""
    with pytest.raises(UnsafeUrlError):
        validate_public_http_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://10.0.0.5/",
        "http://192.168.1.1/admin",
        "http://172.16.0.1/",
        # The service names inside this project's own docker network.
        "http://db:5432/",
        "http://backend:8000/",
    ],
)
def test_blocks_private_and_docker_network_addresses(url):
    with pytest.raises(UnsafeUrlError):
        validate_public_http_url(url)


def test_blocks_cloud_metadata_link_local():
    """169.254.169.254 is the canonical SSRF target for stealing instance
    credentials."""
    with pytest.raises(UnsafeUrlError):
        validate_public_http_url("http://169.254.169.254/latest/meta-data/")


def test_blocks_ipv6_mapped_ipv4_loopback():
    """::ffff:127.0.0.1 reaches loopback while looking like a v6 address —
    it has to be judged on the IPv4 address it actually hits."""
    with pytest.raises(UnsafeUrlError):
        validate_public_http_url("http://[::ffff:127.0.0.1]/")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://127.0.0.1:5432/_hello",
        "ftp://example.com/x",
        "data:text/html,<h1>hi</h1>",
        "javascript:alert(1)",
    ],
)
def test_blocks_non_http_schemes(url):
    with pytest.raises(UnsafeUrlError):
        validate_public_http_url(url)


@pytest.mark.parametrize("url", ["", "   ", "not a url", "https://", "http:///path"])
def test_rejects_malformed_input(url):
    with pytest.raises(UnsafeUrlError):
        validate_public_http_url(url)


def test_error_message_is_shown_to_the_user_so_it_must_be_readable():
    """This string reaches the UI as the 422 detail — it should say what to
    do, not leak internals."""
    with pytest.raises(UnsafeUrlError) as exc:
        validate_public_http_url("http://192.168.0.1/")
    assert "interna" in str(exc.value).lower()
