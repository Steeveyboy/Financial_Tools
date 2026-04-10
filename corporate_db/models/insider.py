"""
Insider model — board member / insider stub for future use (Agent 7).

This model is intentionally minimal.  Future agents will extend it with
additional columns (compensation, share ownership, transaction history, etc.)
and the corresponding Alembic migrations.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from .base import Base

if TYPE_CHECKING:
    from .company import Company


class Insider(Base):
    """Board member or insider associated with a :class:`~corporate_db.models.company.Company`.

    Attributes:
        id:             Auto-incrementing primary key.
        company_id:     FK to :class:`~corporate_db.models.company.Company`.
        name:           Full legal name.
        role:           Job title / role, e.g. ``CEO``, ``Director``, ``CFO``.
        is_board_member: Whether the person sits on the board.
        is_insider:     Whether the person is classified as a reporting insider.
        start_date:     Date the role began (nullable).
        end_date:       Date the role ended (nullable; ``None`` = current).
        created_at:     Record creation timestamp (UTC).
        updated_at:     Last-modified timestamp, auto-updated on every write (UTC).
        company:        Parent company (many-to-one).
    """

    __tablename__ = "insiders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    is_board_member: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    is_insider: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )

    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationship
    company: Mapped["Company"] = relationship("Company", back_populates="insiders")

    def __repr__(self) -> str:
        return f"<Insider(name={self.name!r}, role={self.role!r})>"
