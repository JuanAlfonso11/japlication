from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import JobSource
from app.schemas.job_match import MatchResult
from app.services import work_authorization


class WorkAuthInfo(BaseModel):
    """Donde exige la oferta poder trabajar (services/work_authorization.py).

    Se calcula al servir, no se guarda: es una regex sobre la descripcion y
    la ubicacion, y asi mejorar el detector corrige todas las vacantes sin
    migrar nada.
    """

    label: str
    regions: list[str] = Field(default_factory=list)
    explicit: bool = False
    no_sponsorship: bool = False
    #: Lo rellenan los endpoints que conocen al usuario: True = su pais queda
    #: fuera; False = cabe; None = no se sabe (perfil sin pais, u oferta que
    #: no nombra ninguno).
    blocks_you: Optional[bool] = None


def _work_auth_for(description: Optional[str], location: Optional[str]) -> Optional[WorkAuthInfo]:
    wa = work_authorization.detect(description, location)
    if not wa.restricted:
        return None
    return WorkAuthInfo(
        label=wa.label or "",
        regions=list(wa.regions),
        explicit=wa.explicit,
        no_sponsorship=wa.no_sponsorship,
    )


def annotate_work_auth(items, user_country: Optional[str]) -> None:
    """Marca blocks_you en cada Job/ExternalJobResult ya construido."""
    for item in items:
        info = getattr(item, "work_auth", None)
        if info is None:
            continue
        wa = work_authorization.WorkAuth(tuple(info.regions), info.explicit, info.no_sponsorship)
        info.blocks_you = wa.blocks(user_country)


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
    deadline: Optional[date] = None
    apply_url: Optional[str] = None
    apply_ats: Optional[str] = None
    apply_email: Optional[str] = None
    source_url: Optional[str] = None
    requires_cover_letter: bool = False


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
    deadline: Optional[date] = None
    apply_url: Optional[str] = None
    apply_ats: Optional[str] = None
    apply_email: Optional[str] = None
    requires_cover_letter: bool = False
    #: La oferta ya no existe en su origen (services/liveness.py).
    closed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    match: Optional[MatchResult] = None
    work_auth: Optional[WorkAuthInfo] = None

    @model_validator(mode="after")
    def _fill_work_auth(self):
        if self.work_auth is None:
            self.work_auth = _work_auth_for(self.description, self.location)
        return self


class JobListResponse(BaseModel):
    items: list[Job]
    total: int


class ApplyOption(BaseModel):
    title: str
    link: Optional[str] = None


ExternalProvider = str  # "himalayas"|"arbeitnow"|"remotive"|"jobicy"|"remotejobs_org"|"themuse"
ExperienceLevel = str  # "internship" | "entry" | "mid" | "senior" | "lead" — see app/services/experience_level.py


class ExternalJobResult(BaseModel):
    """One normalized, not-yet-persisted search result from a live,
    no-auth external provider (Himalayas, Arbeitnow, Remotive, Jobicy,
    RemoteJobs.org, or The Muse). Shaped like `Job` (minus id/timestamps)
    plus `external_id` + `source`, used together to import it via
    `POST /jobs/search/import`."""

    external_id: str
    source: ExternalProvider
    source_url: Optional[str] = None
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
    deadline: Optional[date] = None
    apply_url: Optional[str] = None
    apply_ats: Optional[str] = None
    apply_email: Optional[str] = None
    posted_at_text: Optional[str] = None
    via: Optional[str] = None
    apply_options: list[ApplyOption] = Field(default_factory=list)
    thumbnail: Optional[str] = None
    work_auth: Optional[WorkAuthInfo] = None

    @model_validator(mode="after")
    def _fill_work_auth(self):
        if self.work_auth is None:
            self.work_auth = _work_auth_for(self.description, self.location)
        return self


class ExternalJobsSearchResponse(BaseModel):
    provider: ExternalProvider
    results: list[ExternalJobResult]
    next_page_token: Optional[str] = None
    page: Optional[int] = None
    has_more: bool = False


class ExternalJobImportRequest(BaseModel):
    source: ExternalProvider
    external_id: str


class AggregateSourceStatus(BaseModel):
    """Per-provider outcome of GET /jobs/search/aggregate — lets the
    frontend show "3 results from Remotive" or surface which source
    failed without hiding the results the other sources did return."""

    provider: ExternalProvider
    count: int
    error: Optional[str] = None


class AggregateSearchResponse(BaseModel):
    results: list[ExternalJobResult]
    sources: list[AggregateSourceStatus]


class AutoImportResponse(BaseModel):
    """Result of POST /jobs/search/auto-import — how many new jobs were
    queued for Home's swipe deck, and per-provider status same as the
    aggregate search this reuses under the hood."""

    imported: int
    query: Optional[str] = None
    sources: list[AggregateSourceStatus]
