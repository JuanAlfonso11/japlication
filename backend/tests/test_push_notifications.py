import pytest

from app.core.config import settings
from app.services import push_notifications


def test_is_configured_false_without_credentials_path(monkeypatch):
    monkeypatch.setattr(settings, "FIREBASE_CREDENTIALS_PATH", None)
    assert push_notifications.is_configured() is False


def test_is_configured_true_with_credentials_path(monkeypatch):
    monkeypatch.setattr(settings, "FIREBASE_CREDENTIALS_PATH", "/some/path.json")
    assert push_notifications.is_configured() is True


def test_send_push_no_ops_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "FIREBASE_CREDENTIALS_PATH", None)
    # Should return False rather than raise, even though no Firebase app
    # could ever be initialized without credentials.
    assert push_notifications.send_push("some-token", "Title", "Body") is False


def test_send_push_raises_unregistered_error_for_caller_to_handle(monkeypatch):
    """A dead token (app uninstalled/reinstalled) must propagate as
    UnregisteredError, not be swallowed like a transient failure — this is
    what lets callers (jobs.py, check_stale_applications.py) catch it
    specifically and delete the dead row from device_tokens."""
    from firebase_admin import messaging

    monkeypatch.setattr(settings, "FIREBASE_CREDENTIALS_PATH", "/fake/path.json")
    monkeypatch.setattr(push_notifications, "_app", lambda: object())

    def _raise_unregistered(message, app=None):
        raise messaging.UnregisteredError("token is unregistered")

    monkeypatch.setattr(messaging, "send", _raise_unregistered)

    with pytest.raises(messaging.UnregisteredError):
        push_notifications.send_push("dead-token", "Title", "Body")


def test_send_push_returns_false_on_other_firebase_errors(monkeypatch):
    """A transient failure (network, quota, ...) must NOT propagate — only
    UnregisteredError does. Everything else keeps the original
    never-raises-for-transient-failures contract."""
    from firebase_admin import messaging
    from firebase_admin.exceptions import UnavailableError

    monkeypatch.setattr(settings, "FIREBASE_CREDENTIALS_PATH", "/fake/path.json")
    monkeypatch.setattr(push_notifications, "_app", lambda: object())

    def _raise_unavailable(message, app=None):
        raise UnavailableError("FCM temporarily unavailable")

    monkeypatch.setattr(messaging, "send", _raise_unavailable)

    assert push_notifications.send_push("some-token", "Title", "Body") is False
