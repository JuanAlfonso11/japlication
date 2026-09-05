"""Push notifications via Firebase Cloud Messaging (the Firebase Admin SDK).

Same graceful-degradation pattern as every other optional external service
in this app (SMTP, Claude, ...): without FIREBASE_CREDENTIALS_PATH set, this
silently no-ops instead of raising, so the app stays fully usable without a
Firebase project configured.

Verified end-to-end on a real device: FCM reports a successful send (this
function returns True) even when nothing visibly appears on the phone —
Android only auto-displays a "notification"-type message like this one in
the system tray when the app is backgrounded/killed. With the app in the
foreground, Capacitor just delivers it silently to JS (a
'pushNotificationReceived' listener, not currently wired up) instead. Not a
bug — if a foreground toast/banner is ever wanted too, that's what that
listener + @capacitor/local-notifications would be for.
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
    """Sends one push notification. Never raises for a transient failure —
    an unreachable FCM is not worth failing the caller's request over (e.g.
    the auto-import flow that triggers this), so those failures are just
    logged and this returns False.

    The one deliberate exception: `firebase_admin.messaging.UnregisteredError`
    (the token is permanently dead — app uninstalled/reinstalled) propagates
    instead of being swallowed, so callers that loop over this user's device
    tokens can catch it specifically and delete the dead row from
    `device_tokens`. Without that, a dead token sits there forever, silently
    failing the exact same way on every future sweep. Every current caller
    (jobs.py's auto-import notification, check_stale_applications.py's daily
    reminder) already catches this — see those call sites."""
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
    except messaging.UnregisteredError:
        logger.info("Device token %s... is unregistered — caller should prune it.", token[:12])
        raise
    except FirebaseError as exc:
        logger.warning("Push notification failed for token %s...: %s", token[:12], exc)
        return False
