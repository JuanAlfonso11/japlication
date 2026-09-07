from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContactInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    phone: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None


class Skill(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    category: Optional[str] = None
    level: Optional[str] = None
    years_experience: Optional[float] = None


class Experience(BaseModel):
    model_config = ConfigDict(extra="allow")

    company: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    location: Optional[str] = None
    bullets: list[str] = Field(default_factory=list)
    skills_used: list[str] = Field(default_factory=list)


class Education(BaseModel):
    model_config = ConfigDict(extra="allow")

    institution: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class Certification(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    issuer: Optional[str] = None
    date: Optional[str] = None


class Language(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    level: Optional[str] = None


class ScreeningAnswer(BaseModel):
    """One reusable answer to a question application forms keep asking.

    Deliberately free-form (`question` is a string, not an enum): every job
    board words these differently, and the point is that the user can paste
    whatever a given form actually asked and keep the answer for next time.
    """

    model_config = ConfigDict(extra="allow")

    question: str = Field(min_length=1, max_length=300)
    answer: str = Field(default="", max_length=2000)


class CareerProfileUpsert(BaseModel):
    headline: Optional[str] = None
    summary: Optional[str] = None
    contact_info: ContactInfo = Field(default_factory=ContactInfo)
    skills: list[Skill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    screening_answers: list[ScreeningAnswer] = Field(default_factory=list)


class CVUploadResult(BaseModel):
    """A draft profile parsed from an uploaded PDF — never persisted by
    itself. The frontend pre-fills the profile editor with it; the user
    still has to review and hit Save (PUT /profile) for it to take effect."""

    profile: CareerProfileUpsert
    generated_by: str  # "ai" | "heuristic"
    warnings: list[str] = Field(default_factory=list)


class ProfileImprovementResult(BaseModel):
    """A rewritten headline/summary/experience-bullets proposal for the
    BASE profile — same never-persisted-until-Save rule as CVUploadResult.
    Per-job tailoring (a different, narrower rewrite for one specific
    posting) stays resume_adapter.py's job; this is for the profile that
    every one of those starts from."""

    profile: CareerProfileUpsert
    change_log: list[str] = Field(default_factory=list)
    generated_by: str  # "ai" | "manual"


class CareerProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    headline: Optional[str] = None
    summary: Optional[str] = None
    contact_info: dict[str, Any] = Field(default_factory=dict)
    skills: list[dict[str, Any]] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[dict[str, Any]] = Field(default_factory=list)
    languages: list[dict[str, Any]] = Field(default_factory=list)
    screening_answers: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
