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
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# .env loading — anchored to repo root regardless of the working directory
# ---------------------------------------------------------------------------
# This file lives at  <repo_root>/corporate_db/config.py
# The .env file lives at <repo_root>/.env
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

if _ENV_FILE.is_file():
    # override=False: shell / process environment variables always win
    _loaded = load_dotenv(_ENV_FILE, override=False)
    logger.debug(
        "Loaded .env from %s (new variables applied: %s)", _ENV_FILE, _loaded
    )
else:
    logger.debug(
        ".env file not found at %s — relying solely on the shell environment.",
        _ENV_FILE,
    )

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

if not DATABASE_URL:
    logger.warning(
        "DATABASE_URL is not set; falling back to local SQLite file "
        "'corporate_db.sqlite3'."
    )
    DATABASE_URL = "sqlite:///corporate_db.sqlite3"
else:
    # Log connection target without exposing credentials
    try:
        from sqlalchemy.engine.url import make_url as _make_url

        _u = _make_url(DATABASE_URL)
        logger.info(
            "DATABASE_URL loaded — driver: %s | host: %s | database: %s",
            _u.drivername,
            _u.host or "(local)",
            _u.database,
        )
    except Exception:
        logger.info("DATABASE_URL loaded (could not parse URL for masked logging).")

# ---------------------------------------------------------------------------
# SQL echo / debug logging
# ---------------------------------------------------------------------------
_echo_raw: str = os.environ.get("ECHO_SQL", "0")
ECHO_SQL: bool = _echo_raw.strip().lower() in {"1", "true", "yes", "on"}
logger.debug("ECHO_SQL=%s (raw env value: %r)", ECHO_SQL, _echo_raw)
