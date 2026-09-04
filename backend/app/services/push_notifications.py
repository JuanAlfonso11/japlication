"""Push notifications via Firebase Cloud Messaging (the Firebase Admin SDK).

Same graceful-degradation pattern as every other optional external service
in this app (SMTP, Claude, ...): without FIREBASE_CREDENTIALS_PATH set, this
silently no-ops instead of raising, so the app stays fully usable without a
Firebase project configured.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("jobflow.push")


def is_configured() -> bool:
    return bool(settings.FIREBASE_CREDENTIALS_PATH)


@lru_cache
def _app():
    import firebase_admin
    from firebase_admin import credentials

    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
    return firebase_admin.initialize_app(cred)


def send_push(token: str, title: str, body: str, data: Optional[dict[str, str]] = None) -> bool:
    """Sends one push notification. Never raises — a bad/stale device token
    or an unreachable FCM is not worth failing the caller's request over
    (e.g. the auto-import flow that triggers this), so failures are just
    logged. Returns whether the send actually succeeded."""
    if not is_configured():
        return False

    from firebase_admin import messaging
    from firebase_admin.exceptions import FirebaseError

    message = messaging.Message(
        token=token,
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
    )
    try:
        messaging.send(message, app=_app())
        return True
    except FirebaseError as exc:
        logger.warning("Push notification failed for token %s...: %s", token[:12], exc)
        return False
