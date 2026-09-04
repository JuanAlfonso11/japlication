"""Shared rate-limiter instance (slowapi/limits), applied to the
auth endpoints most worth throttling (login, register, resend-verification)
against brute-force/spam. Kept as its own module so both main.py (which
registers the exception handler) and auth.py (which decorates routes with
it) can import it without a circular import.

Caveat: Docker Desktop for Windows/Mac's networking (WSL2-backed) can
obscure the real client IP for traffic hitting a published port — in
practice this means the limiter may end up treating multiple devices
behind that NAT as one bucket rather than truly per-device. Not a concern
for this app's actual threat model (a private, Tailscale-only, single-user
app), so not worth a reverse-proxy just to fix X-Forwarded-For handling.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
