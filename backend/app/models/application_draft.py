import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

#: Estados de un borrador (CHECK de la tabla, migraciones 0019 y 0020).
#:
#:   preparing  -- el agente lo esta armando (justo despues del swipe)
#:   needs_user -- faltan respuestas que solo el usuario puede dar
#:   ready      -- completo; espera a que el usuario lo apruebe
#:   scheduled  -- modo automatico: sale en scheduled_for si nadie lo deshace
#:   submitting -- saliendo ahora mismo
#:   submitted  -- enviado y confirmado
#:   handoff    -- no pudo salir solo (CAPTCHA, sin confirmacion, destino que
#:                 el agente no envia): el usuario lo envia en la pagina real
#:   failed     -- no se pudo preparar
#:   cancelled  -- el usuario lo descarto
DRAFT_PREPARING = "preparing"
DRAFT_READY = "ready"
DRAFT_NEEDS_USER = "needs_user"
DRAFT_FAILED = "failed"
DRAFT_SCHEDULED = "scheduled"
DRAFT_SUBMITTING = "submitting"
DRAFT_SUBMITTED = "submitted"
DRAFT_HANDOFF = "handoff"
DRAFT_CANCELLED = "cancelled"
DRAFT_STATUSES = (
    DRAFT_PREPARING,
    DRAFT_READY,
    DRAFT_NEEDS_USER,
    DRAFT_FAILED,
    "approved",
    DRAFT_SCHEDULED,
    DRAFT_SUBMITTING,
    DRAFT_SUBMITTED,
    DRAFT_HANDOFF,
    DRAFT_CANCELLED,
)
#: Los que ya no cambian solos.
DRAFT_FINAL = (DRAFT_SUBMITTED, DRAFT_CANCELLED)

#: Por donde sale la candidatura.
CHANNEL_GREENHOUSE = "greenhouse"  # el formulario publico, lo llena el contenedor agent
CHANNEL_EMAIL = "email"            # la oferta pide enviarla a un correo
CHANNEL_EXTERNAL = "external"      # cualquier otro sitio: la envia el usuario


class ApplicationDraft(Base):
    """El borrador que el agente prepara para una candidatura.

    Uno por candidatura: volver a prepararlo lo reemplaza. `content` guarda el
    borrador entero: los campos con su respuesta y de donde salio
    (apply_agent.draft.Draft.to_dict()), los avisos de las puertas
    (`gates`), la auditoria de hechos del CV y la carta (`grounding`) y, si
    salio, el informe del envio (`submission`).
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
    channel: Mapped[str] = mapped_column(Text, nullable=False, default=CHANNEL_GREENHOUSE)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="SET NULL"), nullable=True
    )
    cover_letter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cover_letters.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __mapper_args__ = {"eager_defaults": True}
