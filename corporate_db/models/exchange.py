"""
Exchange model — represents a stock exchange (NYSE, NASDAQ, TSX, TSXV, …).

Each Exchange has a one-to-many relationship with :class:`~corporate_db.models.company.Company`.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .company import Company


class Exchange(Base):
    """Stock exchange entity.

    Attributes:
        id:         Auto-incrementing primary key.
        code:       Short exchange code, e.g. ``NYSE``, ``NASDAQ``, ``TSX``.
        name:       Full exchange name, e.g. *New York Stock Exchange*.
        country:    Country where the exchange is domiciled.
        currency:   Primary trading currency code, e.g. ``USD``, ``CAD``.
        timezone:   IANA timezone string, e.g. ``America/New_York``.
        created_at: Record creation timestamp (UTC).
        updated_at: Last-modified timestamp, auto-updated on every write (UTC).
        companies:  Back-populated list of companies listed on this exchange.
    """

    __tablename__ = "exchanges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

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

    # Relationship — populated lazily by SQLAlchemy
    companies: Mapped[List["Company"]] = relationship(
        "Company",
        back_populates="exchange",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Exchange(code={self.code!r}, name={self.name!r})>"
