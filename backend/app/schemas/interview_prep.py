from pydantic import BaseModel, Field


class InterviewQuestion(BaseModel):
    question: str
    #: tecnica | brecha | requisito | empresa — drives how the UI colours it,
    #: and "brecha" in particular is the one worth flagging loudly.
    category: str
    #: Why this posting in particular is likely to produce this question.
    why: str = ""
    #: Grounded in the profile's own bullets. For a gap, these are honest
    #: framings rather than answers, because inventing experience is exactly
    #: what the rest of the system refuses to do.
    talking_points: list[str] = Field(default_factory=list)


class InterviewPrepResponse(BaseModel):
    questions: list[InterviewQuestion] = Field(default_factory=list)
    #: "ai" when an LLM rewrote the grounded material, "manual" for the
    #: rule-based sheet — which is the default and works with no API key.
    generated_by: str = "manual"
