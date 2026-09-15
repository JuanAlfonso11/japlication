from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExternalJobCache(Base):
    """One row per external search result seen recently, keyed by the
    provider and that provider's own id for the posting.

    A search returns a normalized posting — title, company, description,
    requirements, the lot. "Agregar a la cola" then sends back only the
    provider and the id, and the server rebuilds the row from what it
    already has instead of paying for a second request to a source that
    may be rate-limited, keyed, or simply slow.

    "What it already has" used to mean a dict in the process's memory, one
    per connector, emptied by every restart: the watchdog recovering a
    container, `docker compose up -d --build`, shipping an APK. Coming back
    to a search already on screen and pressing the button answered "this
    search result has expired — run the search again", which is a strange
    thing to hear about a posting the user is looking at. Here it survives
    the restart; app.services.external_jobs.result_cache handles expiry.

    Not user data and not a `jobs` row: nothing here has been added to
    anyone's queue. It is a scratch copy of a public listing, and dropping
    the whole table at any moment costs at most one repeated search.
    """

    __tablename__ = "external_job_cache"

    source: Mapped[str] = mapped_column(String, primary_key=True)
    external_id: Mapped[str] = mapped_column(String, primary_key=True)
    #: The normalized result exactly as the search endpoint returned it,
    #: JSON-serialized (so `posted_at` is an ISO string in here).
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
