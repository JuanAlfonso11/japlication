from pydantic import BaseModel


class CVIssue(BaseModel):
    severity: str  # "error" | "warning" | "info"
    category: str  # "completeness" | "impact" | "skills_breadth" | "ats_safety"
    message: str


class CVCategoryScore(BaseModel):
    score: float
    issues: list[CVIssue]


class CVEvaluation(BaseModel):
    overall_score: float
    band: str  # "Necesita trabajo" | "En progreso" | "Sólido" | "Excelente"
    categories: dict[str, CVCategoryScore]
    top_issues: list[CVIssue]
    strengths: list[str]
    summary: str
    summary_generated_by: str  # "ai" | "manual"
