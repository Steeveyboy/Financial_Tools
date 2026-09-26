"""
Reusable column groups shared across models.

Keeping these in one place is what makes the "every table has exactly these two
audit columns" rule in ``docs/DATA_MODEL.md`` true by construction rather than
by everyone remembering.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from findata.db.types import UTCDateTime

__all__ = ["UTCDateTime", "TimestampMixin"]


class TimestampMixin:
    """``created_at`` / ``updated_at``, on every table without exception.

    These describe the *warehouse row* — when we wrote it and when we last
    changed it — never the underlying event. Event time belongs in a named
    domain column (``published_at``, ``trade_date``).

    Both defaults are server-side, so the database clock is authoritative and
    rows written by bulk INSERT (which bypasses Python-side defaults) still get
    values.
    """

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
