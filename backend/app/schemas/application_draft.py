from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ApplicationDraftOut(BaseModel):
    """El borrador tal como lo ve la app. `content` es Draft.to_dict(): los
    campos con su respuesta, de donde salio cada una, y los motivos por los
    que no podria enviarse solo (`review_reasons` / `review_reason_texts`)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    ats: str
    form_url: str
    status: str
    auto_eligible: bool
    content: dict[str, Any]
    error: Optional[str] = None
    updated_at: Optional[datetime] = None


class AgentReadiness(BaseModel):
    """Si el perfil tiene lo basico para que el agente arme borradores utiles."""

    ready: bool
    missing: list[str]
