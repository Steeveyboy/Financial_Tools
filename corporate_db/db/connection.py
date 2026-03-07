"""
Database connection utilities for corporate_db.

Provides three public helpers:

* :func:`get_engine` — returns a (cached) SQLAlchemy :class:`~sqlalchemy.engine.Engine`.
* :func:`get_session` — context manager that yields a :class:`~sqlalchemy.orm.Session`
  with automatic commit/rollback handling.
* :func:`init_db` — creates all tables defined in ``Base.metadata`` (dev / testing).

The database URL and echo flag are read from :mod:`corporate_db.config`.
If you need a different URL at runtime, set the ``DATABASE_URL`` environment
variable **before** importing this module (or before calling :func:`get_engine`
for the first time).

Usage example::

    from corporate_db.db.connection import get_session
    from corporate_db.models.company import Company

    with get_session() as session:
        companies = session.query(Company).filter_by(is_active=True).all()
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from corporate_db.config import DATABASE_URL, ECHO_SQL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singletons (lazily initialised)
# ---------------------------------------------------------------------------
_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def get_engine() -> Engine:
    """Return a cached :class:`~sqlalchemy.engine.Engine`.

    The engine is created once per process using the URL and echo settings
    from :mod:`corporate_db.config`.  For SQLite connections, ``check_same_thread``
    is disabled so the engine can be safely used across threads (common in
    web frameworks).
    """
    global _engine
    if _engine is None:
        connect_args: dict = {}
        if DATABASE_URL.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        _engine = create_engine(
            DATABASE_URL,
            echo=ECHO_SQL,
            connect_args=connect_args,
        )

        # Enable WAL mode on SQLite for better concurrency
        if DATABASE_URL.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, _connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        logger.debug("Created engine for %s", DATABASE_URL)

    return _engine


def _get_session_factory() -> sessionmaker:
    """Return a cached :class:`~sqlalchemy.orm.sessionmaker` bound to the engine."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionFactory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager that yields a database session.

    Commits on clean exit, rolls back on any exception, and always closes
    the session::

        with get_session() as session:
            session.add(Company(name="Acme Corp", ticker="ACM", exchange_id=1))
            # commits automatically on exit

    Raises:
        Any exception raised inside the ``with`` block (after rolling back).
    """
    factory = _get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables defined in ``Base.metadata``.

    This is intended for development and testing.  In production, use
    ``alembic upgrade head`` instead so that schema changes are tracked.

    Also seeds a small set of well-known exchanges if the ``exchanges`` table
    is empty.
    """
    # Import Base through the models package so that all model classes are
    # registered on Base.metadata before create_all() is called.
    from corporate_db.models import Base  # noqa: PLC0415

    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("Database tables created (or already exist).")

    _seed_exchanges(engine)


def _seed_exchanges(engine: Engine) -> None:
    """Insert default exchange records if the table is empty."""
    from corporate_db.models.exchange import Exchange  # noqa: PLC0415

    with get_session() as session:
        if session.query(Exchange).count() == 0:
            defaults = [
                Exchange(
                    code="NYSE",
                    name="New York Stock Exchange",
                    country="United States",
                    currency="USD",
                    timezone="America/New_York",
                ),
                Exchange(
                    code="NASDAQ",
                    name="NASDAQ Stock Market",
                    country="United States",
                    currency="USD",
                    timezone="America/New_York",
                ),
                Exchange(
                    code="TSX",
                    name="Toronto Stock Exchange",
                    country="Canada",
                    currency="CAD",
                    timezone="America/Toronto",
                ),
                Exchange(
                    code="TSXV",
                    name="TSX Venture Exchange",
                    country="Canada",
                    currency="CAD",
                    timezone="America/Toronto",
                ),
            ]
            session.add_all(defaults)
            logger.info("Seeded %d default exchanges.", len(defaults))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print(f"Database initialised at: {DATABASE_URL}")
