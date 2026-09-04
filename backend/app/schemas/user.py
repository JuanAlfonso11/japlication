import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.services.disposable_email import is_disposable_email

_UPPERCASE_RE = re.compile(r"[A-Z]")
_DIGIT_RE = re.compile(r"\d")
_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)

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

    @field_validator("email")
    @classmethod
    def _reject_disposable_email(cls, v: str) -> str:
        if is_disposable_email(v):
            raise ValueError(
                "No se permiten correos temporales/desechables — usa un correo permanente."
            )
        return v


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


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User


class ResendVerificationResponse(BaseModel):
    sent: bool
    detail: str
