from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import ApplicationStatus, SwipeDecision


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    company: str
    location: Optional[str] = None
    remote_type: Optional[str] = None
    employment_type: Optional[str] = None
    seniority: Optional[str] = None


class DecisionRequest(BaseModel):
    decision: SwipeDecision
    # Optional — set by the job-detail page's "Apply" button once the user
    # has generated a tailored resume/cover letter there, so the resulting
    # Application is created with those already attached instead of a bare
    # decision. Swiping from Home's queue omits these; a right swipe on a
    # job that requires a cover letter still gets one auto-generated (or
    # reused) server-side — see swipe_decision in applications.py.
    resume_version_id: Optional[UUID] = None
    cover_letter_id: Optional[UUID] = None


class ApplicationUpdate(BaseModel):
    status: Optional[ApplicationStatus] = None
    notes: Optional[str] = None
    applied_at: Optional[datetime] = None


class Application(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    job_id: UUID
    status: ApplicationStatus
    decision: Optional[SwipeDecision] = None
    match_score: Optional[float] = None
    resume_version_id: Optional[UUID] = None
    cover_letter_id: Optional[UUID] = None
    notes: Optional[str] = None
    applied_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    job: Optional[JobSummary] = None
