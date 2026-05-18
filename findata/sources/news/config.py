"""
config.py

Loads configuration from environment variables for the news_articles module.

Required:
    DATABASE_URL  - SQLAlchemy connection string (shared with market_data)
                    e.g. postgresql://user:pass@localhost:5432/resonance
                         sqlite:///resonance.db

Optional:
    NEWS_LOG_LEVEL - Logging level (default: INFO)
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()


def get_db_url() -> str:
    """Return the database connection string, raising clearly if unset."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set.\n"
            "Set it before running:\n"
            '  export DATABASE_URL="sqlite:///resonance.db"'
        )
    return url


LOG_LEVEL: str = os.environ.get("NEWS_LOG_LEVEL", "INFO").upper()
