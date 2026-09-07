"""Gives every request an id, and makes sure nothing fails silently.

Two jobs:

1. **Correlation.** Each request gets a short id, echoed back in the
   `X-Request-Id` header and included in the body of any 500. When something
   breaks, "salió un error, id a1b2c3" is enough to find the exact row in
   `error_logs` — instead of guessing from a timestamp.

2. **Capture.** An unhandled exception is recorded (with its traceback, the
   route, and the user if there was a session) and then converted into a
   clean 500 that names the id. Without this, the traceback went to stdout
   and the user got an opaque error with no way to tell you which one.

Not recorded: 4xx responses. A 401 on an expired token or a 422 on a
mistyped URL is the app working correctly, and burying real failures under
thousands of those is how a log stops being read.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.security import decode_access_token
from app.services.error_logger import format_exception, new_request_id, record_error


def _user_id_from_request(request: Request):
    """Best-effort: who was this happening to?

    Decoding the token here rather than depending on `get_current_user` —
    middleware runs outside FastAPI's dependency injection, and an
    unauthenticated or malformed request must still be logged, just without
    a user attached.
    """
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    subject = decode_access_token(auth[7:].strip())
    if not subject:
        return None
    try:
        import uuid

        return uuid.UUID(subject)
    except (ValueError, AttributeError):
        return None


class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = new_request_id()
        # Stashed on state so route handlers (and the exception handlers in
        # main.py) can reach the same id this middleware will report.
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001 - the whole point is to catch everything
            kind, message, stack = format_exception(exc)
            await record_error(
                request_id=request_id,
                source="backend",
                kind=kind,
                message=message,
                stack=stack,
                method=request.method,
                # `request.url.path` and not the full URL: a query string can
                # carry search terms, tokens, or a shared job posting's
                # tracking parameters, and none of that belongs in a log.
                path=request.url.path,
                status_code=500,
                user_id=_user_id_from_request(request),
                user_agent=request.headers.get("user-agent"),
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": (
                        "Algo falló de nuestro lado. Si vuelve a pasar, "
                        f"pásale este código a quien mantiene la app: {request_id}"
                    ),
                    "request_id": request_id,
                },
                headers={"X-Request-Id": request_id},
            )

        response.headers["X-Request-Id"] = request_id
        return response
