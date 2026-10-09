import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WidgetToken(Base):
    """La credencial del widget "Próxima vacante" de un teléfono.

    No es una sesión: solo abre /widget/* (ver el router), es decir, ver la
    cola y pasar, guardar o deshacer. Así el widget decide sin abrir la app,
    y si esa credencial se filtra no da acceso al perfil, al CV ni a nada
    más. Se guarda solo su hash, como los refresh tokens.

    Una por instalación (`device_id`, un UUID que genera el propio teléfono):
    emitir una nueva para el mismo teléfono revoca la anterior, aunque sea de
    otra cuenta. Cerrar sesión o restablecer la contraseña también la revoca.
    """

    __tablename__ = "widget_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
