"""
Shared column types and value normalizers.

Every ``*_at`` column in the warehouse is ``DateTime(timezone=True)``. Naive
datetimes must not reach the database: comparing an aware value to a naive one
raises ``TypeError`` in Python and silently misinterprets the instant in SQL.

:func:`ensure_utc` is the single place that normalization happens. Extractors
call it on any timestamp they parse out of an upstream feed.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator

_logger = logging.getLogger(__name__)


def ensure_utc(value: datetime | date | None) -> datetime | None:
    """Return *value* as a timezone-aware UTC :class:`~datetime.datetime`.

    - ``None`` passes through, so callers can hand over optional fields.
    - A naive ``datetime`` is **assumed to already be UTC** and stamped as such.
      Upstream feeds that publish local times without an offset are
      indistinguishable from UTC ones at this layer; the assumption is recorded
      here rather than repeated at each call site.
    - An aware ``datetime`` is converted to UTC.
    - A plain ``date`` becomes midnight UTC.

    This is what keeps the FNSPID date filter from raising
    ``can't compare offset-naive and offset-aware datetimes`` (REPO_REVIEW #3).
    """
    if value is None:
        return None

    # date but not datetime — datetime is a subclass of date, so order matters.
    if not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def utc_now() -> datetime:
    """Return the current time as an aware UTC datetime.

    Prefer a column ``server_default=func.now()`` over calling this — the
    database clock is the one consistent source. Use this only where a Python
    value is genuinely required.
    """
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """A ``timestamptz`` column that is tz-aware UTC on *every* backend.

    Postgres ``timestamptz`` round-trips an aware datetime natively. SQLite has
    no such type: it stores the value fine but hands it back **naive**, so the
    same code reading the same logical row gets an aware value in production and
    a naive one in tests — and comparing the two raises ``TypeError``.

    This decorator closes that gap at the type level rather than asking every
    call site to remember:

    - on the way in, :func:`ensure_utc` normalizes whatever it is given;
    - on the way out, a naive value is stamped UTC and an aware one converted.

    DDL is unchanged — ``impl`` is ``DateTime(timezone=True)``, so migrations and
    ``alembic check`` see an ordinary ``timestamptz``.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ARG002
        return ensure_utc(value)

    def process_result_value(self, value, dialect):  # noqa: ARG002
        if value is None:
            return None
        if value.tzinfo is None:
            # SQLite: stored as UTC by process_bind_param, returned naive.
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
