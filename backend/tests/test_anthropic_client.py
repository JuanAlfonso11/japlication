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
