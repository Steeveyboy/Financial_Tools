"""Database connection utilities for ``corporate_db``.

Provides three public helpers:

* :func:`get_engine` — returns a cached SQLAlchemy engine.
* :func:`get_session` — yields a session with automatic commit/rollback.
* :func:`init_db` — creates tables and seeds default exchanges.

The database URL and echo flag are read from :mod:`corporate_db.config`.
If you need a different URL at runtime, set ``DATABASE_URL`` before importing
this module or before calling :func:`get_engine` for the first time.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from corporate_db.config import DATABASE_URL, ECHO_SQL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singletons (lazily initialised)
# ---------------------------------------------------------------------------
_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def _safe_url(url: str) -> str:
    """Return a log-safe representation of *url* with the password masked."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return "<unparseable URL>"


def get_engine() -> Engine:
    """Return a cached :class:`~sqlalchemy.engine.Engine`.

    The engine is created once per process using the URL and echo settings
    from :mod:`corporate_db.config`.  For SQLite connections, ``check_same_thread``
    is disabled so the engine can be safely used across threads (common in
    web frameworks).
    """
    global _engine
    if _engine is not None:
        logger.debug("Returning cached engine (%s).", _safe_url(DATABASE_URL))
        return _engine

    logger.info("Creating new SQLAlchemy engine — %s", _safe_url(DATABASE_URL))

    connect_args: dict = {}
    if DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        logger.debug("SQLite detected — disabling check_same_thread.")

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
            logger.debug("SQLite PRAGMAs set: journal_mode=WAL, foreign_keys=ON.")

    logger.info(
        "Engine created — dialect: %s, echo: %s.",
        _engine.dialect.name,
        ECHO_SQL,
    )
    return _engine


def _get_session_factory() -> sessionmaker:
    """Return a cached :class:`~sqlalchemy.orm.sessionmaker` bound to the engine."""
    global _SessionFactory
    if _SessionFactory is None:
        logger.debug("Creating session factory.")
        _SessionFactory = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        logger.debug("Session factory created.")
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
    logger.debug("Session opened (id=%s).", id(session))
    try:
        yield session
        session.commit()
        logger.debug("Session committed (id=%s).", id(session))
    except Exception as exc:
        logger.warning(
            "Session rollback triggered by %s: %s (id=%s).",
            type(exc).__name__,
            exc,
            id(session),
        )
        session.rollback()
        raise
    finally:
        session.close()
        logger.debug("Session closed (id=%s).", id(session))


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

    logger.info("Initialising database schema — %s", _safe_url(DATABASE_URL))
    engine = get_engine()

    table_names = list(Base.metadata.tables.keys())
    logger.debug("Tables registered on Base.metadata: %s", table_names)

    Base.metadata.create_all(engine)
    logger.info(
        "Schema sync complete — %d table(s) ensured: %s.",
        len(table_names),
        table_names,
    )

    _seed_exchanges(engine)


def _seed_exchanges(engine: Engine) -> None:
    """Insert default exchange records if the table is empty."""
    from corporate_db.models.exchange import Exchange  # noqa: PLC0415

    logger.debug("Checking whether exchanges table needs seeding.")
    with get_session() as session:
        count = session.query(Exchange).count()
        if count == 0:
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
        else:
            logger.debug("Exchanges table already has %d row(s) — skipping seed.", count)


def main() -> None:
    """Initialise the database when invoked as a script or module."""
    logging.basicConfig(level=logging.INFO)
    init_db()
    print(f"Database initialised at: {DATABASE_URL}")


if __name__ == "__main__":
    main()
