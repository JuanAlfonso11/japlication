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
