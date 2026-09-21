from datetime import date, datetime
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
    #: Para el aviso "Cerrada" del pipeline (services/liveness.py).
    closed_at: Optional[datetime] = None
    deadline: Optional[date] = None


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
    #: A right swipe only saves to the pipeline. This is the job-detail
    #: page's "Apply" button saying the user is applying right now (it opens
    #: the employer's posting), which is what stamps applied_at and
    #: auto-attaches a cover letter.
    mark_applied: bool = False


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


class ApplicationListResponse(BaseModel):
    items: list[Application]
    total: int


class EmailApplyAttachment(BaseModel):
    filename: str
    size_bytes: int


class EmailApplyPreview(BaseModel):
    """Exactamente lo que se enviaria. Ver services/apply_by_email.py.

    `blockers` no vacio = no se puede enviar, y dice por que. La vista previa
    se devuelve igual, para que el usuario vea el correo aunque falte algo."""

    to: Optional[str] = None
    reply_to: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    attachments: list[EmailApplyAttachment] = []
    #: Hay que devolverla tal cual al enviar. Si lo que se enviaria cambio
    #: desde la vista previa, el envio se rechaza.
    fingerprint: Optional[str] = None
    blockers: list[str] = []


class EmailApplySend(BaseModel):
    fingerprint: str
