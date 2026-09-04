from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GenerationSource
from app.schemas.application import JobSummary


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
    job: Optional[JobSummary] = None


class ReusableResumeSuggestion(BaseModel):
    """Response of GET /jobs/{job_id}/resume/reusable — a previously
    generated resume for a *different* job whose required skills overlap
    enough with this job's that it's worth offering as a drop-in reuse
    instead of generating (and storing) yet another near-duplicate
    version. `similarity` is a 0-1 Jaccard overlap over canonicalized
    skill names; None/0 means nothing crossed the reuse threshold."""

    resume_version: Optional[ResumeVersion] = None
    similarity: float = 0.0
    source_job_title: Optional[str] = None
    source_company: Optional[str] = None
