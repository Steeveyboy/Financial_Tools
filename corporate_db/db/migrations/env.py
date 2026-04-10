"""
Alembic environment file for corporate_db.

This file is loaded by Alembic when running migration commands.  It:

1. Reads the database URL from :mod:`corporate_db.config` (which in turn
   reads ``DATABASE_URL`` from the environment, falling back to SQLite).
2. Imports all ORM models so that Alembic's autogenerate feature can
   diff ``Base.metadata`` against the current database schema.
3. Configures ``render_as_batch=True`` so that SQLite column alterations
   work correctly (SQLite does not support ``ALTER COLUMN``).
"""

from __future__ import annotations

import logging
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# ---------------------------------------------------------------------------
# Alembic Config object — gives access to values in alembic.ini
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging (if present)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# ---------------------------------------------------------------------------
# Import all models so that Base.metadata is fully populated
# ---------------------------------------------------------------------------
# The import order matters: base must be imported before the models that
# reference it, and the models __init__ handles that correctly.
from corporate_db.models import Base  # noqa: E402
from corporate_db.models import Exchange, Company, Insider  # noqa: E402, F401

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Database URL — prefer environment variable, fall back to alembic.ini
# ---------------------------------------------------------------------------
def _get_url() -> str:
    """Return the database URL to use for migrations."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    # Fall back to the value set in alembic.ini (may be a placeholder)
    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url and ini_url != "driver://user:pass@host/dbname":
        return ini_url
    # Ultimate fallback: local SQLite file
    return "sqlite:///corporate_db.sqlite3"


# ---------------------------------------------------------------------------
# Offline migrations  (alembic upgrade head --sql)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations without a live database connection.

    Generates SQL scripts to stdout / a file.
    """
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE support
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations  (alembic upgrade head)
# ---------------------------------------------------------------------------
def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    url = _get_url()

    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTER TABLE support
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
