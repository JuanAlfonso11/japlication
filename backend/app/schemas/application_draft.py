from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.application import JobSummary


class ApplicationDraftOut(BaseModel):
    """El borrador tal como lo ve la app. `content` es Draft.to_dict() mas lo
    que anade el pipeline: `gates` (requisitos de la oferta), `grounding`
    (auditoria de hechos del CV y la carta), `documents`, `email` (vista
    previa si sale por correo), `review_reasons` / `review_reason_texts`,
    `pending_required`, `handoff_reason` y `log`."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    ats: str
    form_url: str
    status: str
    channel: str = "greenhouse"
    auto_eligible: bool
    content: dict[str, Any]
    error: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    resume_version_id: Optional[UUID] = None
    cover_letter_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ApplicationDraftListItem(BaseModel):
    """Una fila de la bandeja "Aplicaciones en curso": sin el contenido entero."""

    id: UUID
    application_id: UUID
    job_id: UUID
    status: str
    channel: str
    auto_eligible: bool
    error: Optional[str] = None
    pending_count: int = 0
    review_reason_texts: list[str] = []
    handoff_reason: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    job: Optional[JobSummary] = None


class DraftAnswers(BaseModel):
    #: {clave_del_campo: valor}. None o "" borra la respuesta.
    answers: dict[str, Any]
    #: El usuario leyo la carta generada por IA y la da por buena.
    cover_letter_reviewed: Optional[bool] = None


class AgentReadiness(BaseModel):
    """Si el perfil tiene lo basico para que el agente arme borradores utiles."""

    ready: bool
    missing: list[str]


ApplyMode = Literal["save", "review", "auto"]


class ApplySettings(BaseModel):
    apply_mode: ApplyMode
    daily_auto_limit: int
    undo_minutes: int
    #: El servidor tiene el contenedor que envia formularios de Greenhouse.
    agent_available: bool
    auto_sent_today: int = 0


class ApplySettingsUpdate(BaseModel):
    apply_mode: ApplyMode
