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

from typing import Any, Optional

from app.core.config import settings


def get_anthropic_client() -> Optional[Any]:
    """The configured client, or None if AI is not available at all.

    None means "there is no point trying": no key, or the SDK is not
    installed. A key that exists but is rejected still returns a client
    here — that failure belongs to the call, not to the construction, and
    the caller's own except block handles it.
    """
    if not settings.ANTHROPIC_API_KEY:
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
