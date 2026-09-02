from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import JobSource
from app.schemas.job_match import MatchResult


class JobImportRequest(BaseModel):
    url: str


class SkillRequirement(BaseModel):
    name: str
    importance: str = "required"  # required | nice_to_have


class JobCreate(BaseModel):
    """Manual job creation — same body shape as a parsed Job, for pasting a
    description directly."""

    title: str
    company: str
    location: Optional[str] = None
    remote_type: Optional[str] = None
    employment_type: Optional[str] = None
    seniority: Optional[str] = None
    description: str
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    skills_required: list[SkillRequirement] = Field(default_factory=list)
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    posted_at: Optional[datetime] = None
    source_url: Optional[str] = None


class Job(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    imported_by: Optional[UUID] = None
    source: JobSource
    source_url: Optional[str] = None
    title: str
    company: str
    location: Optional[str] = None
    remote_type: Optional[str] = None
    employment_type: Optional[str] = None
    seniority: Optional[str] = None
    description: str
    requirements: list[Any] = Field(default_factory=list)
    responsibilities: list[Any] = Field(default_factory=list)
    skills_required: list[Any] = Field(default_factory=list)
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    posted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    match: Optional[MatchResult] = None


class JobListResponse(BaseModel):
    items: list[Job]
    total: int
