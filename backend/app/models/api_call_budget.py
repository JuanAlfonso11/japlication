from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApiCallBudget(Base):
    """One row per (provider, calendar day) — tracks how many times a
    monthly-quota external API (Adzuna, SerpApi) has been called today, so
    app.services.api_budget can enforce a daily cap and never let an
    unattended background sweep silently blow through a monthly quota
    (see docs/PUBLIC_APIS_RESEARCH.md for each provider's actual limit)."""

    __tablename__ = "api_call_budgets"

    provider: Mapped[str] = mapped_column(String, primary_key=True)
    call_date: Mapped[date] = mapped_column(Date, primary_key=True)
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
