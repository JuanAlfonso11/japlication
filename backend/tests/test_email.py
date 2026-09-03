from app.core.config import settings
from app.services import email


def test_is_configured_false_without_smtp_host(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    assert email.is_configured() is False


def test_is_configured_true_with_smtp_host(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    assert email.is_configured() is True


def test_send_without_smtp_configured_does_not_raise(monkeypatch, caplog):
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    # Should log the message instead of attempting a real connection.
    email._send("user@example.com", "Subject", "text body", "<p>html body</p>")


def test_send_verification_email_builds_message_and_logs_when_unconfigured(monkeypatch, caplog):
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    import logging

    with caplog.at_level(logging.WARNING, logger="jobflow.email"):
        email.send_verification_email("user@example.com", "Camila Reyes", "https://app/verify-email?token=abc")
    assert any("user@example.com" in record.message for record in caplog.records)


def test_send_raises_email_error_on_smtp_failure(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)

    class FakeSMTP:
        def __init__(self, *a, **k):
            raise OSError("connection refused")

    import smtplib

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    import pytest

    with pytest.raises(email.EmailError):
        email._send("user@example.com", "Subject", "text", "<p>html</p>")
