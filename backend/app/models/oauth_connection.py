import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OAuthConnection(Base):
    """A user's stored OAuth2 tokens for an external provider that requires
    per-user authorization (currently: Upwork). Distinct from Google Jobs/
    SerpApi, which authenticates with one shared server-side API key rather
    than a per-user OAuth grant.

    Tokens are stored as plain text, matching this project's personal-use,
    single-tenant scope (see backend/README.md); a shared/multi-user
    deployment should encrypt them at rest.
    """

    __tablename__ = "oauth_connections"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_oauth_connections_user_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_type: Mapped[str] = mapped_column(Text, nullable=False, default="Bearer")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
