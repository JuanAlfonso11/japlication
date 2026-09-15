"""One HTTP client for the 15 job connectors.

Each connector used to open its own `httpx.AsyncClient(timeout=20.0)` with the
timeout written as a literal, and none of them retried anything. Three
consequences the review called out:

* **A transient blip was a missing source.** No retry at all, so one dropped
  TCP handshake removed that provider from the results — reported as a failure
  the user sees, for something that would have worked on the second try.

* **A source that was down stayed hammered.** Every search re-attempted it at
  full rate and paid the full timeout waiting. With several providers down the
  aggregate spent its whole 12s deadline on connections that were never going
  to answer, crowding out the ones that would.

* **Changing the timeout meant editing 15 files.** And the aggregate's deadline
  is 12s while each connector waited up to 20s, so a slow provider kept a
  connection alive well past the point where anyone was still listening.

What this adds, in one place:

- a configurable timeout (`EXTERNAL_JOBS_TIMEOUT_SECONDS`), defaulting below
  the aggregate deadline so a straggler is abandoned rather than orphaned;
- one retry with jittered backoff, for the failures that are actually
  transient (timeouts, connection errors, 5xx, 429) and never for the ones
  that are not (4xx — a bad request retried is a bad request twice);
- a circuit breaker per provider: after repeated failures it is skipped
  outright for a cooldown, so a dead source costs ~0ms instead of the timeout.

Deliberately NOT a connection pool shared across calls: `AsyncClient` is
cheap to create, and a module-level client outliving the event loop it was
built on is a known source of "Event loop is closed" errors in tests.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("jobflow.external_jobs")

USER_AGENT = (
    "Mozilla/5.0 (compatible; JobFlowAI/1.0; +https://jobflow.ai/bot) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

#: Statuses worth a second attempt. 5xx is the server admitting it broke; 429
#: is "slow down", which one backoff often satisfies. Everything else in 4xx
#: means the request itself was wrong and will be wrong again.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

#: Consecutive failures before a provider is skipped, and for how long.
#: Three, not one: a single blip is what the retry is for. The cooldown is
#: shorter than the 15-minute search cache, so a recovered source comes back
#: within the same session rather than staying dark until a restart.
_BREAKER_THRESHOLD = 3
_BREAKER_COOLDOWN_SECONDS = 120.0


class ProviderUnavailable(RuntimeError):
    """The circuit breaker is open — this provider is being skipped on purpose.

    Connectors let this propagate; the aggregate reports it in `sources` like
    any other per-provider failure, which is exactly what it is: a failure
    reported without paying for it again.
    """


class _Breaker:
    """Consecutive-failure counter per provider. Process-local by design.

    Nothing here needs to survive a restart — a fresh process retrying a dead
    source once is the correct behaviour, and sharing this state through the
    database would add a write to the hot path of every search.
    """

    def __init__(self) -> None:
        self._failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}

    def is_open(self, provider: str) -> bool:
        until = self._open_until.get(provider)
        if until is None:
            return False
        if time.monotonic() >= until:
            # Cooldown elapsed: let exactly one attempt through. If it fails,
            # record_failure re-opens immediately.
            self._open_until.pop(provider, None)
            self._failures[provider] = _BREAKER_THRESHOLD - 1
            return False
        return True

    def record_success(self, provider: str) -> None:
        self._failures.pop(provider, None)
        self._open_until.pop(provider, None)

    def record_failure(self, provider: str) -> None:
        count = self._failures.get(provider, 0) + 1
        self._failures[provider] = count
        if count >= _BREAKER_THRESHOLD:
            self._open_until[provider] = time.monotonic() + _BREAKER_COOLDOWN_SECONDS
            logger.warning(
                "circuito abierto para %s tras %d fallos seguidos; se omite %.0fs",
                provider,
                count,
                _BREAKER_COOLDOWN_SECONDS,
            )

    def snapshot(self) -> dict[str, float]:
        """Providers currently being skipped -> seconds left. For diagnostics."""
        now = time.monotonic()
        return {p: round(t - now, 1) for p, t in self._open_until.items() if t > now}


_breaker = _Breaker()


def open_circuits() -> dict[str, float]:
    return _breaker.snapshot()


def is_circuit_open(provider: str) -> bool:
    """For connectors that keep their own client (linkedin_jobs) and so cannot
    go through `get()`, but should still be skipped while they are failing."""
    return _breaker.is_open(provider)


def record_failure(provider: str) -> None:
    """Same case: let a connector with its own client feed the breaker."""
    _breaker.record_failure(provider)


def record_success(provider: str) -> None:
    _breaker.record_success(provider)


def timeout_seconds() -> float:
    return float(settings.EXTERNAL_JOBS_TIMEOUT_SECONDS)


async def get(
    provider: str,
    url: str,
    *,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: Optional[float] = None,
    retries: int = 1,
) -> httpx.Response:
    """GET `url` on behalf of `provider`, with retry and breaker applied.

    Returns the response for the caller to validate — status handling stays in
    each connector, because what counts as an error differs per API (some
    answer 200 with an error body), and every connector already ends with its
    own `if resp.status_code != 200: raise XError(...)`.

    Transport failures propagate as the same `httpx.HTTPError` family the
    connectors already catch, so their existing `except httpx.HTTPError` blocks
    keep working untouched. `ProviderUnavailable` is the one new exception: the
    circuit is open and this call never touched the network.
    """
    if _breaker.is_open(provider):
        raise ProviderUnavailable(
            f"{provider} no responde desde hace rato; se omite temporalmente."
        )

    merged_headers = {"User-Agent": USER_AGENT}
    if headers:
        merged_headers.update(headers)

    effective_timeout = timeout if timeout is not None else timeout_seconds()

    # Request-level kwargs are built conditionally: `headers` is only passed
    # when the caller actually supplied some. The default User-Agent rides on
    # the client instead, so a connector that asks for no headers sends the
    # same plain `get(url, params=...)` call it always did.
    request_kwargs: dict[str, Any] = {"params": params}
    if headers:
        request_kwargs["headers"] = merged_headers

    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(effective_timeout, connect=min(10.0, effective_timeout)),
                headers=merged_headers,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url, **request_kwargs)
        except (httpx.TimeoutException, httpx.TransportError):
            if attempt < retries:
                await _backoff(attempt)
                continue
            _breaker.record_failure(provider)
            raise

        status = getattr(resp, "status_code", 200)

        if status in _RETRYABLE_STATUS and attempt < retries:
            await _backoff(attempt)
            continue

        # Out of retries on a bad status: hand the response back rather than
        # raising. Interpreting a status is the connector's job — several of
        # these APIs answer 200 with an error body, and each already has its
        # own `if resp.status_code != 200: raise XError(...)`. Raising here
        # would duplicate that decision in the wrong place.
        #
        # A 4xx is still "the provider answered", so it never counts against
        # the breaker; only transport failures and 5xx do.
        if status >= 500:
            _breaker.record_failure(provider)
        else:
            _breaker.record_success(provider)
        return resp

    raise AssertionError("unreachable: the loop always returns, continues or raises")


async def _backoff(attempt: int) -> None:
    """Jittered backoff. The jitter matters more than the delay: without it,
    15 providers that all failed at the same instant retry at the same instant.
    """
    base = 0.25 * (2 ** attempt)
    await asyncio.sleep(base + random.uniform(0, 0.25))
