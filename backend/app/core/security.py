import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str | UUID, expires_minutes: Optional[int] = None) -> str:
    expire_delta = timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expire_delta
    to_encode: dict[str, Any] = {"sub": str(subject), "exp": expire}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token() -> str:
    """A high-entropy opaque value (not a JWT) — the server is the only
    place that can tell it's valid, by looking up its hash in
    `refresh_tokens`. That's what makes it revocable (log out, a stolen
    token, ...) unlike a self-contained JWT, which nothing can invalidate
    before its own expiry."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """SHA-256, not bcrypt — this token is already 48 bytes of random
    entropy (unlike a human password), so a slow, salted KDF buys nothing
    here and would just add needless cost to every refresh request. Storing
    the hash rather than the raw token means a DB leak alone doesn't hand
    out usable sessions."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_access_token(token: str) -> Optional[str]:
    """Returns the subject (user id) encoded in the token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
    return payload.get("sub")


def create_state_token(subject: str | UUID, purpose: str, expires_minutes: int = 10) -> str:
    """A short-lived, purpose-scoped JWT used for a signed link a user
    clicks from outside the app (e.g. the email-verification link) — ties
    the callback back to the user it was minted for and prevents it being
    confused with a normal session token or reused for a different
    purpose."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode = {"sub": str(subject), "purpose": purpose, "exp": expire}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_state_token(token: str, purpose: str) -> Optional[str]:
    """Returns the subject encoded in a create_state_token() token, or None
    if invalid/expired/wrong purpose."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
    if payload.get("purpose") != purpose:
        return None
    return payload.get("sub")
