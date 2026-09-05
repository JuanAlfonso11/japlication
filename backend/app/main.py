from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.api.v1.routers import (
    app_update,
    applications,
    auth,
    cover_letters,
    jobs,
    match,
    notifications,
    profile,
    resumes,
    system,
)
from app.core.config import settings
from app.core.rate_limit import limiter

app = FastAPI(title=settings.PROJECT_NAME, version="1.0.0")
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many attempts — please wait a moment and try again."},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Normalize error responses to the {detail, code} shape from API_CONTRACT.md."""
    code = None
    if isinstance(exc.detail, dict):
        body = exc.detail
    else:
        code = getattr(exc, "code", None)
        body = {"detail": exc.detail, "code": code}
    return JSONResponse(status_code=exc.status_code, content=body, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's default 422 body is {detail: [{msg, loc, ...}, ...]} — the
    frontend expects {detail: string} like every other error (see
    http_exception_handler above), so this flattens it to a single readable
    message instead of the raw Pydantic error list."""
    messages = [str(err.get("msg", "")).removeprefix("Value error, ") for err in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "; ".join(messages) or "Invalid request."})


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}


api_router_prefix = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=api_router_prefix)
app.include_router(profile.router, prefix=api_router_prefix)
app.include_router(jobs.router, prefix=api_router_prefix)
app.include_router(match.router, prefix=api_router_prefix)
app.include_router(applications.router, prefix=api_router_prefix)
app.include_router(resumes.router, prefix=api_router_prefix)
app.include_router(cover_letters.router, prefix=api_router_prefix)
app.include_router(notifications.router, prefix=api_router_prefix)
app.include_router(app_update.router, prefix=api_router_prefix)
app.include_router(system.router, prefix=api_router_prefix)
