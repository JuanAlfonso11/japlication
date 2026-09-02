from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GenerationSource


class ResumeGenerateRequest(BaseModel):
    tone: Optional[str] = None


class ResumeVersion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    career_profile_id: UUID
    job_id: Optional[UUID] = None
    title: str
    content: dict[str, Any]
    change_log: list[Any] = Field(default_factory=list)
    generated_by: GenerationSource
    created_at: datetime
