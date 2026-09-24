"""One place that knows how to build an Anthropic client.

Seven services call the Messages API (match_engine, resume_adapter,
cover_letter_generator, cv_upload, cv_evaluator, profile_improver,
interview_prep). Each used to construct `anthropic.Anthropic(api_key=...)`
on its own, which meant any change to how the client is configured had to
be made seven times and would silently work in six of them.

That is not hypothetical. An API key that is not scoped to a workspace is
rejected with:

    400 invalid_request_error: This API key is not scoped to a workspace, so
    this request must include the anthropic-workspace-id header

Every one of those seven call sites swallows exceptions and falls back to
its offline path, so the failure would have looked exactly like "the AI
features just aren't very good" — no error, no log line, nothing. Building
the client in one function makes that class of bug impossible to have in
only some features.

Returns None instead of raising when the key or the `anthropic` package is
missing, because every caller already treats None as "use the offline
path". Callers keep their own try/except around the actual API call.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger("jobflow.ai")

# Count of swallowed AI failures per feature, since process start. The
# fallbacks are deliberate and correct — an AI outage should never be an
# error page — but "correct" was being paid for with total blindness: if the
# key expired, hit its quota, or lost workspace scope, every feature quietly
# served its offline result forever and nothing anywhere said so. You keep
# paying Anthropic and keep receiving TF-IDF.
_failure_counts: dict[str, int] = {}
_failure_lock = threading.Lock()


def log_ai_failure(feature: str, exc: BaseException) -> None:
    """Record that an AI call failed and we fell back. Never raises.

    Called from the `except` block of every service that degrades to an
    offline path. Safe from a worker thread (several of these run under
    `asyncio.to_thread`), which is why it writes to the logger and an
    in-process counter rather than touching the database.
    """
    with _failure_lock:
        _failure_counts[feature] = _failure_counts.get(feature, 0) + 1
        total = _failure_counts[feature]

    logger.warning(
        "AI_FALLBACK feature=%s error=%s: %s (fallo #%d desde el arranque; "
        "se usó la ruta offline)",
        feature,
        type(exc).__name__,
        exc,
        total,
        exc_info=exc,
    )


def ai_failure_counts() -> dict[str, int]:
    """Snapshot of swallowed AI failures per feature, since process start."""
    with _failure_lock:
        return dict(_failure_counts)


_spend_day: Optional[str] = None
_spend_counts: dict[str, int] = {}

#: Buckets with their own daily count. Match scoring is by far the highest
#: volume caller — one call per (user, job) pair, for every user — and used
#: to share a single counter with everything else. On a busy day it spent the
#: whole budget by itself and every *interactive* feature (importing a CV,
#: improving it, a cover letter) silently dropped to its offline path for the
#: rest of the day: users saw "Analizado sin IA" with a perfectly valid key.
#: Each bucket now gets its own ceiling, so scoring can only starve itself.
BUCKET_INTERACTIVE = "interactive"
BUCKET_SCORING = "scoring"


def _within_daily_budget(bucket: str = BUCKET_INTERACTIVE) -> bool:
    """Runaway-loop guard for the one API here that costs real money.

    Adzuna and SerpApi are budgeted in services/api_budget.py against their
    monthly *quotas*. Anthropic has no quota to run out of — it just bills —
    so nothing capped it at all: a loop that re-scored the same jobs, or a
    sweep over an unexpectedly large result set, would run until the invoice
    showed up. And because every caller swallows failures into an offline
    fallback, a spend spike produced no visible error either.

    Counted in-process rather than in the database because this is called
    from `asyncio.to_thread` workers with no event loop of their own, and
    try_consume_budget() is async. That means the count resets when the
    container restarts — acceptable for a stop-the-bleeding ceiling set far
    above normal use, not acceptable as a billing control. The real ceiling
    is the spend limit in the Anthropic console; set one there too.
    """
    global _spend_day
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _failure_lock:
        if _spend_day != today:
            _spend_day = today
            _spend_counts.clear()
        count = _spend_counts.get(bucket, 0) + 1
        _spend_counts[bucket] = count

    limit = (
        settings.ANTHROPIC_DAILY_SCORING_BUDGET
        if bucket == BUCKET_SCORING
        else settings.ANTHROPIC_DAILY_CALL_BUDGET
    )
    if count > limit:
        if count == limit + 1:  # log the crossing once, not every call after
            logger.error(
                "AI_BUDGET_EXCEEDED bucket=%s se alcanzo el tope diario de %d llamadas a Anthropic. "
                "Las funciones de IA de este grupo usaran la ruta offline hasta manana (UTC). "
                "Si esto no fue un bucle inesperado, sube el tope en la configuracion.",
                bucket,
                limit,
            )
        return False
    return True


def get_anthropic_client(bucket: str = BUCKET_INTERACTIVE) -> Optional[Any]:
    """The configured client, or None if AI is not available at all.

    None means "there is no point trying": no key, the SDK is not installed,
    or today's spend ceiling for `bucket` is already reached. A key that
    exists but is rejected still returns a client here — that failure belongs
    to the call, not to the construction, and the caller's own except block
    handles it.
    """
    if not settings.ANTHROPIC_API_KEY:
        return None
    if not _within_daily_budget(bucket):
        return None
    try:
        import anthropic
    except ImportError:
        return None

    headers: dict[str, str] = {}
    if settings.ANTHROPIC_WORKSPACE_ID:
        # Required for keys that are not themselves scoped to a workspace;
        # harmless (and ignored) for keys that are, so it is always sent
        # when configured rather than guessed at per key.
        headers["anthropic-workspace-id"] = settings.ANTHROPIC_WORKSPACE_ID

    return anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        default_headers=headers or None,
    )
