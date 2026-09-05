import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ApplicationStatus, SwipeDecision

application_status_enum = PgEnum(
    ApplicationStatus,
    name="application_status",
    values_callable=lambda enum_cls: [e.value for e in enum_cls],
    create_type=False,
)
swipe_decision_enum = PgEnum(
    SwipeDecision,
    name="swipe_decision",
    values_callable=lambda enum_cls: [e.value for e in enum_cls],
    create_type=False,
)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_applications_user_job"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        application_status_enum, nullable=False, default=ApplicationStatus.queued
    )
    decision: Mapped[SwipeDecision | None] = mapped_column(swipe_decision_enum, nullable=True)
    match_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="SET NULL"), nullable=True
    )
    cover_letter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cover_letters.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Last time check_stale_applications.py pushed a "no movement in a
    # while" reminder for this application — lets the daily check re-remind
    # every STALE_RENOTIFY_DAYS instead of spamming once per run forever.
    stale_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job = relationship("Job", foreign_keys=[job_id], lazy="noload")
