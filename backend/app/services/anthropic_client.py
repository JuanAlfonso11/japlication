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

Local model (Ollama)
--------------------
When OLLAMA_BASE_URL is set, the "client" returned here may be a local
Ollama model behind the same `client.messages.create(...)` surface, so none
of the seven services had to change. Load is split by bucket:

- BUCKET_SCORING (automatic: match score, evaluation summary) goes to Ollama
  first — it is the high-volume part and costs nothing locally — and only
  falls back to Claude if Ollama fails.
- BUCKET_INTERACTIVE (what the user asked for: CV import, improvement,
  tailored resume, letter, interview prep) goes to Claude first, and falls
  back to Ollama when there is no key, the user's daily budget is spent, or
  the Claude call fails. With OLLAMA_ROUTE=all, Ollama goes first here too.

Either way a user only sees the offline path when *both* are unavailable.
"""

from __future__ import annotations

import logging
import threading
import time
from contextvars import ContextVar
from types import SimpleNamespace
from typing import Any, Callable, Optional

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
#: (user_id, bucket) -> calls today. user_id is None for calls made outside a
#: request (scripts, background jobs), which then share one "system" count.
_spend_counts: dict[tuple[Optional[str], str], int] = {}

#: Who the current request is for. Set by get_current_user (api/deps.py) so
#: the budget can be counted per user without threading a user id through
#: all seven AI services. asyncio.to_thread copies the context, so the value
#: is still visible inside the worker threads those services run in.
current_ai_user: ContextVar[Optional[str]] = ContextVar("current_ai_user", default=None)

#: Buckets with their own daily count, per user.
#:
#: BUCKET_INTERACTIVE is what the user explicitly asked for: importing a CV,
#: improving it, a tailored resume, a cover letter, interview prep.
#: BUCKET_SCORING is everything that runs as a side effect the user never
#: sees as "an AI call": the match score of every job they add, and the
#: summary on the CV evaluation card (which ran on every visit to Perfil).
#: Those used to share one global counter with everything else, so a few
#: active users browsing their profile left CV import with no AI for the
#: rest of the day: "Analizado sin IA" with a perfectly valid key. Now one
#: user can only use up their own budget, and automatic calls can only use
#: up the automatic bucket.
BUCKET_INTERACTIVE = "interactive"
BUCKET_SCORING = "scoring"


def _today() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _limit_for(bucket: str) -> int:
    if bucket == BUCKET_SCORING:
        return settings.ANTHROPIC_DAILY_SCORING_BUDGET
    return settings.ANTHROPIC_DAILY_CALL_BUDGET


def _within_daily_budget(bucket: str = BUCKET_INTERACTIVE) -> bool:
    """Runaway-loop guard for the one API here that costs real money.

    Adzuna and SerpApi are budgeted in services/api_budget.py against their
    monthly *quotas*. Anthropic has no quota to run out of — it just bills —
    so nothing capped it at all: a loop that re-scored the same jobs, or a
    sweep over an unexpectedly large result set, would run until the invoice
    showed up. And because every caller swallows failures into an offline
    fallback, a spend spike produced no visible error either.

    Counted per user (see current_ai_user) and in-process rather than in the
    database because this is called from `asyncio.to_thread` workers with no
    event loop of their own, and try_consume_budget() is async. That means
    the count resets when the container restarts — acceptable for a
    per-user fairness ceiling, not acceptable as a billing control. The real
    ceiling is the spend limit in the Anthropic console; set one there too.
    """
    global _spend_day
    user = current_ai_user.get()
    key = (user, bucket)

    today = _today()
    with _failure_lock:
        if _spend_day != today:
            _spend_day = today
            _spend_counts.clear()
        count = _spend_counts.get(key, 0) + 1
        _spend_counts[key] = count

    limit = _limit_for(bucket)
    if count > limit:
        if count == limit + 1:  # log the crossing once, not every call after
            logger.error(
                "AI_BUDGET_EXCEEDED user=%s bucket=%s se alcanzo el tope diario de %d llamadas a "
                "Anthropic. Las funciones de IA de este grupo usaran la ruta offline para este "
                "usuario hasta manana (UTC). Si esto no fue un bucle inesperado, sube el tope en "
                "la configuracion.",
                user or "sistema",
                bucket,
                limit,
            )
        return False
    return True


def ai_budget_exhausted(bucket: str = BUCKET_INTERACTIVE) -> bool:
    """Whether the current user has already used up today's `bucket`.

    Read-only (does not count a call), so a fallback path can tell the user
    "you hit today's limit" instead of the misleading "no AI available".
    """
    if ollama_configured():
        # Out of Claude budget is not out of AI: the local model takes over.
        return False
    key = (current_ai_user.get(), bucket)
    with _failure_lock:
        if _spend_day != _today():
            return False
        return _spend_counts.get(key, 0) > _limit_for(bucket)


def _claude_client(bucket: str) -> Optional[Any]:
    """The configured Claude client, or None if it is not available.

    None means "there is no point trying": no key, the SDK is not installed,
    or the current user's spend ceiling for `bucket` is already reached
    today. A key that exists but is rejected still returns a client here —
    that failure belongs to the call, not to the construction, and the
    caller's own except block handles it.
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


# ---------------------------------------------------------------------------
# Ollama (local model)
# ---------------------------------------------------------------------------

#: After Ollama refuses a connection, skip it for this long instead of making
#: every call wait for the connect timeout first. A PC that is off or an
#: Ollama that is not running then costs one slow call, not one per job.
_OLLAMA_COOLDOWN_SECONDS = 60
_ollama_down_until = 0.0


def ollama_configured() -> bool:
    return bool(settings.OLLAMA_BASE_URL)


def _ollama_available() -> bool:
    return ollama_configured() and time.monotonic() >= _ollama_down_until


def _mark_ollama_down() -> None:
    global _ollama_down_until
    _ollama_down_until = time.monotonic() + _OLLAMA_COOLDOWN_SECONDS


class _OllamaMessages:
    """`messages.create` with the subset of the Anthropic signature the
    services use (system, messages, max_tokens), answered by Ollama's
    /api/chat. The `model` argument is ignored: the services pass the Claude
    model name, and the local one is OLLAMA_MODEL."""

    def create(self, *, messages: list[dict[str, Any]], max_tokens: int = 1024,
               system: Optional[str] = None, **_: Any) -> Any:
        import httpx

        chat = [{"role": "system", "content": system}] if system else []
        chat += [{"role": m["role"], "content": m["content"]} for m in messages]
        payload: dict[str, Any] = {
            "model": settings.OLLAMA_MODEL,
            "messages": chat,
            "stream": False,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            # Ollama's default context is a few thousand tokens and it
            # truncates the prompt silently past that — a CV would lose its
            # first half without any error.
            "options": {"num_predict": max_tokens, "num_ctx": settings.OLLAMA_NUM_CTX},
            # Reasoning models would otherwise spend max_tokens thinking and
            # return an empty answer (the match score only allows 16).
            "think": False,
        }
        timeout = httpx.Timeout(settings.OLLAMA_TIMEOUT_SECONDS, connect=5.0)
        url = settings.OLLAMA_BASE_URL.rstrip("/") + "/api/chat"
        try:
            response = httpx.post(url, json=payload, timeout=timeout)
            if response.status_code == 400 and "think" in response.text:
                # A model without a thinking mode can reject the flag itself.
                payload.pop("think")
                response = httpx.post(url, json=payload, timeout=timeout)
        except httpx.ConnectError:
            _mark_ollama_down()
            raise
        response.raise_for_status()
        data = response.json()

        text = (data.get("message") or {}).get("content") or ""
        stop_reason = "max_tokens" if data.get("done_reason") == "length" else "end_turn"
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason=stop_reason,
            model=settings.OLLAMA_MODEL,
        )


class _OllamaClient:
    def __init__(self) -> None:
        self.messages = _OllamaMessages()


class _FallbackMessages:
    def __init__(self, primary: Any, primary_name: str, fallback: Callable[[], Optional[Any]]) -> None:
        self._primary = primary
        self._primary_name = primary_name
        self._fallback = fallback

    def create(self, **kwargs: Any) -> Any:
        try:
            return self._primary.messages.create(**kwargs)
        except Exception as exc:
            second = self._fallback()
            if second is None:
                raise
            log_ai_failure(f"{self._primary_name}->fallback", exc)
            return second.messages.create(**kwargs)


class _FallbackClient:
    """Tries `primary`; if its call raises, asks `fallback()` for a client
    and retries there. `fallback` is only called when needed, so a Claude
    fallback only spends budget on the calls that actually reach it."""

    def __init__(self, primary: Any, primary_name: str, fallback: Callable[[], Optional[Any]]) -> None:
        self.messages = _FallbackMessages(primary, primary_name, fallback)


def get_anthropic_client(bucket: str = BUCKET_INTERACTIVE) -> Optional[Any]:
    """A client for `bucket`, or None if no AI is available at all.

    Without OLLAMA_BASE_URL this is just the Claude client. With it, load is
    split as described in this module's docstring. Callers only ever see
    `client.messages.create(...)` and keep their own try/except around it.
    """
    if not _ollama_available():
        return _claude_client(bucket)

    ollama = _OllamaClient()
    if bucket == BUCKET_SCORING or settings.OLLAMA_ROUTE == "all":
        return _FallbackClient(ollama, "ollama", lambda: _claude_client(bucket))

    claude = _claude_client(bucket)
    if claude is None:
        return ollama
    return _FallbackClient(claude, "claude", lambda: ollama if _ollama_available() else None)


#: The model thinks before answering, and that thinking counts against
#: max_tokens. Measured on the batch scorer: 685 of 750 tokens were thinking,
#: so a reply that needed 60 was cut off. Every limit here used to be sized
#: for the visible answer alone (16 for a single number, 1500 for interview
#: prep), which is why those features kept falling back to their offline
#: path. This is a ceiling, not a cost: billing is for tokens used.
AI_MAX_TOKENS = 16000

#: For calls that extract or score rather than write (reading a CV, match
#: scores): less thinking, faster and cheaper, same answer. Sent through
#: extra_body because the pinned SDK predates the `output_config` argument.
LOW_EFFORT = {"output_config": {"effort": "low"}}


class TruncatedResponse(RuntimeError):
    """The model hit max_tokens: the reply is cut mid-way, and a cut JSON
    object used to surface only as a puzzling JSONDecodeError in the log."""


def response_text(response: Any) -> str:
    """The reply's text, or TruncatedResponse if it ran out of tokens.

    Every caller already catches exceptions into its offline path; this just
    makes the log say *why* ("se quedó sin tokens") instead of "Unterminated
    string", so raising the limit is the obvious fix."""
    if getattr(response, "stop_reason", None) == "max_tokens":
        raise TruncatedResponse("la respuesta de la IA se quedó sin tokens (max_tokens)")
    return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
