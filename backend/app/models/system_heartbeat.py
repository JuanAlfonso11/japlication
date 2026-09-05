from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemHeartbeat(Base):
    """One row per background job (job_sweep, stale_check, backup,
    watchdog, ...) — each scheduled script POSTs here right after it runs
    (see scripts/*.ps1), so Profile's "Estado del sistema" panel can show
    whether the machinery behind the app is actually alive without the
    user having to open Task Scheduler or the container logs."""

    __tablename__ = "system_heartbeats"

    job_name: Mapped[str] = mapped_column(String, primary_key=True)
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_status: Mapped[str] = mapped_column(String, nullable=False, default="ok")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
