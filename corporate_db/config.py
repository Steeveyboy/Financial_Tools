"""
Configuration for the corporate_db module.

DATABASE_URL is read from the environment variable of the same name.
If the variable is not set, the module falls back to a local SQLite file
``corporate_db.sqlite3`` in the current working directory.

Set ``ECHO_SQL=1`` (or any truthy string) in the environment to enable
SQLAlchemy query logging — useful during development.

Example .env file::

    DATABASE_URL=postgresql+psycopg2://user:pass@localhost/corp_db
    ECHO_SQL=0
"""

import os

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "sqlite:///corporate_db.sqlite3",
)

# ---------------------------------------------------------------------------
# SQL echo / debug logging
# ---------------------------------------------------------------------------
_echo_raw: str = os.environ.get("ECHO_SQL", "0")
ECHO_SQL: bool = _echo_raw.strip().lower() in {"1", "true", "yes", "on"}
