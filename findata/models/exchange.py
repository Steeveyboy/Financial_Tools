"""
models/exchange.py

Trading venues. A small, hand-seeded reference table — see
``findata.db.session._seed_exchanges``.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from findata.db.base import SCHEMA_REFERENCE, Base
from findata.models.mixins import TimestampMixin


class Exchange(TimestampMixin, Base):
    """A stock exchange / trading venue."""

    __tablename__ = "exchanges"
    __table_args__ = {"schema": SCHEMA_REFERENCE}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    #: Short venue code — ``NYSE``, ``TSX``. The natural key.
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    #: Currency the venue trades in.
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    #: IANA timezone name, e.g. ``America/New_York``. Needed to turn a local
    #: session time into an instant.
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    companies: Mapped[List["Company"]] = relationship(  # noqa: F821
        "Company",
        back_populates="exchange",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Exchange(code={self.code!r}, name={self.name!r})>"
