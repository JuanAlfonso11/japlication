import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.services.disposable_email import is_disposable_email

_UPPERCASE_RE = re.compile(r"[A-Z]")
_DIGIT_RE = re.compile(r"\d")
_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


#: bcrypt trunca a 72 BYTES sin avisar. Comprobado en este contenedor con
#: bcrypt 4.0.1: dos contrasenas distintas que compartan los primeros 72 bytes
#: abren la misma sesion. Con max_length=128 eso era alcanzable, y el limite
#: es en bytes, no en caracteres: una contrasena con acentos o emoji llega
#: antes de lo que su longitud sugiere. Se rechaza en vez de truncar, porque
#: truncar en silencio es justo lo que hace el fallo.
_BCRYPT_MAX_BYTES = 72


class _NewPassword(BaseModel):
    """Password rules shared by signup and password reset."""

    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _password_fits_bcrypt(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _BCRYPT_MAX_BYTES:
            raise ValueError(
                f"La contrasena no puede superar los {_BCRYPT_MAX_BYTES} bytes "
                "(los acentos y emoji ocupan mas de uno)."
            )
        return v

    @field_validator("password")
    @classmethod
    def _password_complexity(cls, v: str) -> str:
        missing = []
        if not _UPPERCASE_RE.search(v):
            missing.append("una mayúscula")
        if not _DIGIT_RE.search(v):
            missing.append("un número")
        if not _SPECIAL_RE.search(v):
            missing.append("un carácter especial")
        if missing:
            raise ValueError(f"La contraseña debe incluir al menos {', '.join(missing)}.")
        return v


class UserRegister(_NewPassword):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _reject_disposable_email(cls, v: str) -> str:
        if is_disposable_email(v):
            raise ValueError(
                "No se permiten correos temporales/desechables — usa un correo permanente."
            )
        return v


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(_NewPassword):
    token: str = Field(min_length=1, max_length=2048)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    email_verified: bool
    email_verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    #: Only GET /auth/me fills this; login/register answers leave it False.
    is_admin: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: User


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ResendVerificationResponse(BaseModel):
    sent: bool
    detail: str
