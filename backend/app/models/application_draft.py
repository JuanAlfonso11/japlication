import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

#: Estados de un borrador. Esta fase solo produce los tres primeros; los de
#: envio son de las fases siguientes (ver tasks/agente-aplicacion.md) y ya estan
#: en el CHECK de la tabla para no migrarla en cada fase.
DRAFT_READY = "ready"
DRAFT_NEEDS_USER = "needs_user"
DRAFT_FAILED = "failed"
DRAFT_STATUSES = (DRAFT_READY, DRAFT_NEEDS_USER, DRAFT_FAILED, "approved", "scheduled", "submitted", "cancelled")


class ApplicationDraft(Base):
    """El borrador que el agente prepara para una candidatura.

    Uno por candidatura: volver a prepararlo lo reemplaza. `content` guarda el
    borrador entero tal como lo devuelve apply_agent.draft.Draft.to_dict():
    cada campo con su respuesta, de donde salio, y los motivos de revision.
    Nada de esto se ha enviado: enviar es de una fase posterior.
    """

    __tablename__ = "application_drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    ats: Mapped[str] = mapped_column(Text, nullable=False)
    form_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=DRAFT_READY)
    auto_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __mapper_args__ = {"eager_defaults": True}
