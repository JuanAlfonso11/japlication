from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import GenerationSource
from app.schemas.application import JobSummary


class CoverLetterGenerateRequest(BaseModel):
    tone: Optional[str] = None
    resume_version_id: Optional[UUID] = None


class CoverLetter(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    job_id: UUID
    resume_version_id: Optional[UUID] = None
    content: str
    tone: str
    generated_by: GenerationSource
    created_at: datetime
    job: Optional[JobSummary] = None
