from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GenerationSource
from app.schemas.application import JobSummary


class ResumeGenerateRequest(BaseModel):
    tone: Optional[str] = None
    #: "en"/"es". Omitted means "match the posting" -- the server detects the
    #: job description's language, which is the right default: a CV in the
    #: language the ad was written in is what the reader expects.
    language: Optional[str] = None


class ResumeContentUpdate(BaseModel):
    """The editable parts of a generated resume.

    Only the prose the generator wrote is editable — summary, the skill
    list, and each role's bullets. Company names, titles and dates are not:
    those are facts that live in the career profile, and letting them drift
    per-version is how a CV quietly stops matching the profile it claims to
    be derived from.
    """

    summary: Optional[str] = Field(default=None, max_length=4000)
    skills: Optional[list[str]] = None
    #: Bullets keyed by the experience entry's index in `content.experience`,
    #: so the client can send only what changed.
    experience_bullets: Optional[dict[int, list[str]]] = None


class ResumeVersionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    content: Optional[ResumeContentUpdate] = None


class ResumeVersion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    career_profile_id: UUID
    job_id: Optional[UUID] = None
    title: str
    content: dict[str, Any]
    change_log: list[Any] = Field(default_factory=list)
    language: str = "en"
    generated_by: GenerationSource
    #: Null until the user corrects it. Present in the response so the UI can
    #: show "editado por ti" and so reuse can prefer these.
    edited_at: Optional[datetime] = None
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
