"""Shared rate-limiter instance (slowapi/limits), applied to the
auth endpoints most worth throttling (login, register, resend-verification)
against brute-force/spam. Kept as its own module so both main.py (which
registers the exception handler) and auth.py (which decorates routes with
it) can import it without a circular import.

The app is public (tailscale funnel), so the key has to be the real client
IP: uvicorn runs with --proxy-headers (see backend/Dockerfile), which puts
the X-Forwarded-For address into request.client before get_remote_address
reads it. Without it every request looks like it comes from the proxy and
all visitors share one bucket.
"""

import time

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


class LoginLockout:
    """Per-account throttle for /auth/login, on top of the per-IP limiter.

    The per-IP limit does nothing against a password-guessing run spread over
    many addresses; this counts failures per *email*, whatever IP they come
    from. MAX_FAILURES within WINDOW locks that email for WINDOW seconds, even
    for the right password (otherwise the lock would confirm a correct guess).

    Unknown emails are counted exactly like real ones, so the lock does not
    reopen the "is this address registered?" question the login's dummy hash
    closed.

    ponytail: in-process memory — a container restart clears it and it only
    holds with a single uvicorn worker (today's setup). Move it to a DB table
    if the backend ever runs more than one worker.
    """

    MAX_FAILURES = 10
    WINDOW = 15 * 60
    # Guards memory against a spray of random addresses.
    _PRUNE_OVER = 10_000

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._failures: dict[str, list[float]] = {}

    def _recent(self, email: str) -> list[float]:
        cutoff = self._clock() - self.WINDOW
        recent = [t for t in self._failures.get(email, []) if t > cutoff]
        if recent:
            self._failures[email] = recent
        else:
            self._failures.pop(email, None)
        return recent

    def retry_after(self, email: str) -> int:
        """Seconds until `email` may try again; 0 when it isn't locked."""
        recent = self._recent(email)
        if len(recent) < self.MAX_FAILURES:
            return 0
        return max(1, int(recent[-self.MAX_FAILURES] + self.WINDOW - self._clock()))

    def record_failure(self, email: str) -> None:
        if len(self._failures) > self._PRUNE_OVER:
            for key in list(self._failures):
                self._recent(key)
        self._failures.setdefault(email, []).append(self._clock())

    def reset(self, email: str) -> None:
        self._failures.pop(email, None)


login_lockout = LoginLockout()
