from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MatchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    overall_score: float
    technical_score: float
    experience_score: float
    semantic_score: Optional[float] = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)


class JobMatch(MatchResult):
    id: UUID
    user_id: UUID
    job_id: UUID
    computed_at: datetime
