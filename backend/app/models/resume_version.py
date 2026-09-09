import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import GenerationSource

generation_source_enum = PgEnum(
    GenerationSource,
    name="generation_source",
    values_callable=lambda enum_cls: [e.value for e in enum_cls],
    create_type=False,
)


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    career_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("career_profiles.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_log: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    #: Which language this CV was written in ("en"/"es"). Recorded rather
    #: than inferred so the reuse suggestion never hands a Spanish CV to an
    #: English posting.
    language: Mapped[str] = mapped_column(Text, nullable=False, default="en")
    generated_by: Mapped[GenerationSource] = mapped_column(
        generation_source_enum, nullable=False, default=GenerationSource.ai
    )
    #: Set the first time the user corrects a generated version. Also what
    #: makes this version preferred when a later, similar job looks for a
    #: resume to reuse — see _find_reusable_resume.
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    career_profile = relationship("CareerProfile", back_populates="resume_versions")
    job = relationship("Job", foreign_keys=[job_id], lazy="noload")
