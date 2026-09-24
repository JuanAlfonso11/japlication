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
