import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import JobSource

job_source_enum = PgEnum(
    JobSource,
    name="job_source",
    values_callable=lambda enum_cls: [e.value for e in enum_cls],
    create_type=False,
)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    imported_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[JobSource] = mapped_column(job_source_enum, nullable=False, default=JobSource.url_import)
    source_url: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_type: Mapped[str | None] = mapped_column(String, nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String, nullable=True)
    seniority: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    responsibilities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    skills_required: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    salary_min: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Fecha limite declarada por la oferta, cuando la declara. Un DATE y no un
    #: timestamp a proposito: una oferta dice "hasta el 15 de marzo", no una
    #: hora, y guardar medianoche en algun huso inventaria una precision que el
    #: dato no tiene. NULL significa "no la dice", nunca "no hay plazo".
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_cover_letter: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
