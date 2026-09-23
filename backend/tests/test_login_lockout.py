import pytest

from app.core.rate_limit import LoginLockout, limiter, login_lockout


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_locks_after_max_failures_and_unlocks_after_window():
    clock = FakeClock()
    lockout = LoginLockout(clock=clock)
    for _ in range(LoginLockout.MAX_FAILURES - 1):
        lockout.record_failure("a@x.com")
    assert lockout.retry_after("a@x.com") == 0

    lockout.record_failure("a@x.com")
    assert lockout.retry_after("a@x.com") == LoginLockout.WINDOW
    assert lockout.retry_after("other@x.com") == 0

    clock.now += LoginLockout.WINDOW + 1
    assert lockout.retry_after("a@x.com") == 0


def test_success_resets_the_count():
    lockout = LoginLockout(clock=FakeClock())
    for _ in range(LoginLockout.MAX_FAILURES - 1):
        lockout.record_failure("a@x.com")
    lockout.reset("a@x.com")
    lockout.record_failure("a@x.com")
    assert lockout.retry_after("a@x.com") == 0


def test_old_failures_fall_out_of_the_window():
    clock = FakeClock()
    lockout = LoginLockout(clock=clock)
    for _ in range(LoginLockout.MAX_FAILURES - 1):
        lockout.record_failure("a@x.com")
    clock.now += LoginLockout.WINDOW + 1
    lockout.record_failure("a@x.com")
    assert lockout.retry_after("a@x.com") == 0


@pytest.fixture
def no_ip_limit():
    # Isolate the per-account lock from the per-IP 10/minute limit, which
    # would otherwise answer the 11th request first.
    limiter.enabled = False
    login_lockout.reset("router-test@example.com")
    login_lockout.reset("nobody@example.com")
    yield
    limiter.enabled = True
    login_lockout.reset("router-test@example.com")
    login_lockout.reset("nobody@example.com")


async def test_login_locked_even_with_the_right_password(async_client, user_and_headers, no_ip_limit):
    for _ in range(LoginLockout.MAX_FAILURES):
        r = await async_client.post("/auth/login", json={"email": "router-test@example.com", "password": "wrong"})
        assert r.status_code == 401

    r = await async_client.post("/auth/login", json={"email": "Router-Test@example.com", "password": "Test1234!"})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


async def test_unknown_email_locks_the_same_way(async_client, no_ip_limit):
    for _ in range(LoginLockout.MAX_FAILURES):
        r = await async_client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
        assert r.status_code == 401
    r = await async_client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
    assert r.status_code == 429


async def test_successful_login_clears_failures(async_client, user_and_headers, no_ip_limit):
    for _ in range(LoginLockout.MAX_FAILURES - 1):
        await async_client.post("/auth/login", json={"email": "router-test@example.com", "password": "wrong"})
    r = await async_client.post("/auth/login", json={"email": "router-test@example.com", "password": "Test1234!"})
    assert r.status_code == 200
    r = await async_client.post("/auth/login", json={"email": "router-test@example.com", "password": "wrong"})
    assert r.status_code == 401
