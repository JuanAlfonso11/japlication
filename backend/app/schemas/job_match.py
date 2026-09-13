from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MatchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    overall_score: float
    #: None on any sub-score means the posting gave nothing to judge it by —
    #: the UI hides that bar rather than drawing a 0% or a misleading 100%.
    technical_score: Optional[float] = None
    experience_score: Optional[float] = None
    semantic_score: Optional[float] = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)


class JobMatch(MatchResult):
    id: UUID
    user_id: UUID
    job_id: UUID
    computed_at: datetime


class SkillGap(BaseModel):
    """One skill that keeps costing the user points, with how much."""

    skill: str
    job_count: int
    percentage: int


class SkillGapsResponse(BaseModel):
    gaps: list[SkillGap] = Field(default_factory=list)
    #: How many jobs the aggregate was computed over, so the UI can say
    #: "de las 14 vacantes que guardaste" instead of an unanchored percentage.
    jobs_considered: int = 0
    #: True when there weren't enough saved jobs and this fell back to every
    #: scored posting — the numbers mean something weaker in that case and
    #: the UI says so rather than overstating them.
    based_on_all_matches: bool = False
    summary: Optional[str] = None
