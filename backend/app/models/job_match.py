import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JobMatch(Base):
    __tablename__ = "job_matches"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_job_matches_user_job"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    overall_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    #: NULL means "unknown", not zero and certainly not 100: a posting whose
    #: skills never parsed says nothing about technical fit, and a posting
    #: that states no years requirement says nothing about experience fit.
    #: See match_engine.compute_match, which leaves them out of the average.
    technical_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    experience_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    semantic_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    matched_skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    missing_skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    concerns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
