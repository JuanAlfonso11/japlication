"""Tests for the single place that builds an Anthropic client.

This file exists because of a specific, expensive-to-diagnose failure. An
API key that is not scoped to a workspace is rejected with:

    400 invalid_request_error: This API key is not scoped to a workspace, so
    this request must include the anthropic-workspace-id header

All seven AI services swallow that and fall back to their offline path, so
the symptom was not an error anywhere — it was "the AI features are
mysteriously mediocre". The header now has exactly one place to be wrong,
and these tests watch it.
"""

from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.anthropic_client import get_anthropic_client


class _FakeAnthropic:
    """Captures how the real SDK would have been constructed."""

    last_kwargs: dict = {}

    def __init__(self, **kwargs):
        _FakeAnthropic.last_kwargs = kwargs


@pytest.fixture
def fake_sdk(monkeypatch):
    import anthropic

    _FakeAnthropic.last_kwargs = {}
    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)
    return _FakeAnthropic


def test_returns_none_without_a_key(monkeypatch):
    """None means "do not bother trying" — every caller reads it as
    permission to use its offline path."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    assert get_anthropic_client() is None


def test_returns_none_with_a_blank_key(monkeypatch):
    """An unset env var arrives as "" through docker compose's
    `${ANTHROPIC_API_KEY:-}`, not as None."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    assert get_anthropic_client() is None


def test_sends_the_workspace_header_when_configured(monkeypatch, fake_sdk):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ANTHROPIC_WORKSPACE_ID", "wrkspc_test")

    assert get_anthropic_client() is not None
    headers = fake_sdk.last_kwargs["default_headers"]
    assert headers == {"anthropic-workspace-id": "wrkspc_test"}
    assert fake_sdk.last_kwargs["api_key"] == "test-key"


def test_sends_no_headers_when_no_workspace_is_configured(monkeypatch, fake_sdk):
    """A workspace-scoped key needs no header, and sending an empty dict
    where the SDK expects None is the kind of difference that only shows up
    in production."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ANTHROPIC_WORKSPACE_ID", None)

    assert get_anthropic_client() is not None
    assert fake_sdk.last_kwargs["default_headers"] is None


def test_every_ai_service_builds_its_client_through_the_factory():
    """The actual invariant: no service may construct its own client.

    Seven services call the Messages API. When the workspace header was
    missing, fixing it in six of seven would have looked like it worked —
    the seventh would just have kept quietly falling back. This asserts
    there is nothing to keep in sync.
    """
    import inspect

    from app.services import (
        cover_letter_generator,
        cv_evaluator,
        cv_upload,
        interview_prep,
        match_engine,
        profile_improver,
        resume_adapter,
    )

    servicios = [
        cover_letter_generator,
        cv_evaluator,
        cv_upload,
        interview_prep,
        match_engine,
        profile_improver,
        resume_adapter,
    ]

    for modulo in servicios:
        fuente = inspect.getsource(modulo)
        assert "anthropic.Anthropic(" not in fuente, (
            f"{modulo.__name__} builds its own client instead of calling "
            "get_anthropic_client() — it will miss any future client config."
        )
        assert "get_anthropic_client" in fuente, (
            f"{modulo.__name__} does not use the shared client factory."
        )


@pytest.fixture
def fresh_budget(monkeypatch):
    from app.services import anthropic_client as ac

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ANTHROPIC_DAILY_CALL_BUDGET", 2)
    monkeypatch.setattr(settings, "ANTHROPIC_DAILY_SCORING_BUDGET", 2)
    monkeypatch.setattr(ac, "_spend_day", None)
    monkeypatch.setattr(ac, "_spend_counts", {})
    return ac


def _as_user(ac, user_id, fn):
    import contextvars

    def run():
        ac.current_ai_user.set(user_id)
        return fn()

    return contextvars.copy_context().run(run)


def test_one_user_using_up_their_budget_leaves_others_untouched(fresh_budget):
    """The budget used to be one global counter: a few active users left
    everyone else's CV import with "Analizado sin IA" for the rest of the day."""
    ac = fresh_budget
    for _ in range(2):
        assert _as_user(ac, "ana", ac.get_anthropic_client) is not None
    assert _as_user(ac, "ana", ac.get_anthropic_client) is None
    assert _as_user(ac, "ana", ac.ai_budget_exhausted) is True

    assert _as_user(ac, "beto", ac.get_anthropic_client) is not None
    assert _as_user(ac, "beto", ac.ai_budget_exhausted) is False


def test_automatic_calls_cannot_use_up_the_interactive_budget(fresh_budget):
    """Match scoring and the evaluation summary run without the user asking;
    they must never be why CV import falls back to the offline parse."""
    ac = fresh_budget

    def scoring():
        return ac.get_anthropic_client(bucket=ac.BUCKET_SCORING)

    for _ in range(2):
        assert _as_user(ac, "ana", scoring) is not None
    assert _as_user(ac, "ana", scoring) is None
    assert _as_user(ac, "ana", ac.get_anthropic_client) is not None


def test_budget_exhausted_check_does_not_spend_a_call(fresh_budget):
    ac = fresh_budget
    for _ in range(5):
        assert _as_user(ac, "ana", ac.ai_budget_exhausted) is False
    assert _as_user(ac, "ana", ac.get_anthropic_client) is not None


# ---------------------------------------------------------------------------
# Ollama: load split between the local model and Claude
# ---------------------------------------------------------------------------


class _FakeHttpxResponse:
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        self.text = text

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def ollama(monkeypatch, fresh_budget):
    """Ollama configured and answering; records every request it gets."""
    import httpx

    ac = fresh_budget
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "gemma4:26b")
    monkeypatch.setattr(settings, "OLLAMA_ROUTE", "scoring")
    monkeypatch.setattr(ac, "_ollama_down_until", 0.0)
    requests = []

    def post(url, json, timeout):
        requests.append((url, json))
        return _FakeHttpxResponse(data={"message": {"content": "85"}, "done_reason": "stop"})

    monkeypatch.setattr(httpx, "post", post)
    return SimpleNamespace(ac=ac, requests=requests)


class _FakeClaude:
    def __init__(self, reply="claude", fail=False):
        self.calls = 0
        self._reply, self._fail = reply, fail
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        if self._fail:
            raise RuntimeError("claude down")
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._reply)])


def _text(response):
    return response.content[0].text


def test_automatic_calls_go_to_ollama(ollama, monkeypatch):
    claude = _FakeClaude()
    monkeypatch.setattr(ollama.ac, "_claude_client", lambda bucket: claude)

    client = ollama.ac.get_anthropic_client(bucket=ollama.ac.BUCKET_SCORING)
    reply = client.messages.create(model="claude-x", max_tokens=16, system="sys",
                                   messages=[{"role": "user", "content": "hola"}])

    assert _text(reply) == "85"
    assert claude.calls == 0
    url, payload = ollama.requests[0]
    assert url == "http://ollama:11434/api/chat"
    assert payload["model"] == "gemma4:26b"
    assert payload["messages"][0] == {"role": "system", "content": "sys"}
    assert payload["options"]["num_predict"] == 16
    # Ollama's small default context would silently cut a CV in half.
    assert payload["options"]["num_ctx"] >= 8192


def test_interactive_calls_go_to_claude_first(ollama, monkeypatch):
    claude = _FakeClaude()
    monkeypatch.setattr(ollama.ac, "_claude_client", lambda bucket: claude)

    reply = ollama.ac.get_anthropic_client().messages.create(messages=[{"role": "user", "content": "x"}])
    assert _text(reply) == "claude"
    assert ollama.requests == []


def test_interactive_falls_back_to_ollama_when_claude_fails(ollama, monkeypatch):
    """With a local model available, a Claude error is no longer "Analizado
    sin IA" for the user."""
    monkeypatch.setattr(ollama.ac, "_claude_client", lambda bucket: _FakeClaude(fail=True))

    reply = ollama.ac.get_anthropic_client().messages.create(messages=[{"role": "user", "content": "x"}])
    assert _text(reply) == "85"


def test_interactive_uses_ollama_when_claude_is_unavailable(ollama, monkeypatch):
    """No key, or the user's daily Claude budget is spent."""
    monkeypatch.setattr(ollama.ac, "_claude_client", lambda bucket: None)

    reply = ollama.ac.get_anthropic_client().messages.create(messages=[{"role": "user", "content": "x"}])
    assert _text(reply) == "85"
    assert ollama.ac.ai_budget_exhausted() is False


def test_automatic_calls_fall_back_to_claude_when_ollama_is_off(ollama, monkeypatch):
    """PC off or Ollama not running: fall back, and stop trying Ollama for a
    while instead of paying the connect timeout on every single job."""
    import httpx

    def refused(url, json, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", refused)
    claude = _FakeClaude()
    monkeypatch.setattr(ollama.ac, "_claude_client", lambda bucket: claude)

    client = ollama.ac.get_anthropic_client(bucket=ollama.ac.BUCKET_SCORING)
    assert _text(client.messages.create(messages=[{"role": "user", "content": "x"}])) == "claude"

    # Cooling down: the next client is plain Claude, Ollama is not even tried.
    assert ollama.ac.get_anthropic_client(bucket=ollama.ac.BUCKET_SCORING) is claude


def test_route_all_puts_ollama_first_for_interactive_too(ollama, monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ROUTE", "all")
    claude = _FakeClaude()
    monkeypatch.setattr(ollama.ac, "_claude_client", lambda bucket: claude)

    reply = ollama.ac.get_anthropic_client().messages.create(messages=[{"role": "user", "content": "x"}])
    assert _text(reply) == "85"
    assert claude.calls == 0


def test_a_reply_cut_at_the_token_limit_is_reported_as_such(ollama, monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: _FakeHttpxResponse(
        data={"message": {"content": '{"headline": "Ba'}, "done_reason": "length"}))
    monkeypatch.setattr(ollama.ac, "_claude_client", lambda bucket: None)

    reply = ollama.ac.get_anthropic_client().messages.create(messages=[{"role": "user", "content": "x"}])
    assert reply.stop_reason == "max_tokens"


def test_a_model_without_thinking_mode_is_retried_without_the_flag(ollama, monkeypatch):
    import httpx

    payloads = []

    def post(url, json, timeout):
        payloads.append(dict(json))
        if "think" in json:
            return _FakeHttpxResponse(400, text='{"error":"model does not support thinking"}')
        return _FakeHttpxResponse(data={"message": {"content": "ok"}, "done_reason": "stop"})

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(ollama.ac, "_claude_client", lambda bucket: None)

    reply = ollama.ac.get_anthropic_client().messages.create(messages=[{"role": "user", "content": "x"}])
    assert _text(reply) == "ok"
    assert len(payloads) == 2
