"""
models/insider.py

Board members and insiders associated with an issuer.
"""

from __future__ import annotations

from datetime import date
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, Date, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from findata.db.base import SCHEMA_REFERENCE, Base
from findata.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from .company import Company


class Insider(TimestampMixin, Base):
    """A person with an insider or board relationship to a company."""

    __tablename__ = "insiders"
    __table_args__ = {"schema": SCHEMA_REFERENCE}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{SCHEMA_REFERENCE}.companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    #: ``full_name`` rather than ``name`` — in any join against ``companies``
    #: a bare ``name`` column on both sides is ambiguous to read.
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    is_board_member: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_insider: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    company: Mapped["Company"] = relationship("Company", back_populates="insiders")

    def __repr__(self) -> str:
        return f"<Insider(full_name={self.full_name!r}, role={self.role!r})>"
