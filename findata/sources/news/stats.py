"""
stats.py

Aggregate statistics over the ``articles`` table.

To add a new statistic:
  1. Add a method to ArticleRepository (db/repository.py) that computes it.
  2. Add a (label, method) entry to STATS below.

compute_stats() then picks it up automatically — nothing else needs to change.

Configuration (via .env or environment):
  DATABASE_URL    - SQLAlchemy connection string (required)
  NEWS_LOG_LEVEL  - Logging verbosity (default: INFO)

Usage:
  python -m findata.sources.news.stats
"""

from __future__ import annotations

import logging
from typing import Callable

from sqlalchemy import create_engine

from .config import LOG_LEVEL, get_db_url
from .db.repository import ArticleRepository

_logger = logging.getLogger(__name__)

Stat = Callable[[ArticleRepository], object]

# Each entry is (display label, ArticleRepository method to call).
STATS: list[tuple[str, Stat]] = [
    ("Total articles", ArticleRepository.count_articles),
    ("Unique publishers", ArticleRepository.count_unique_publishers),
]


def compute_stats(repo: ArticleRepository) -> list[tuple[str, object]]:
    """Run every registered statistic against *repo* and return (label, value) pairs."""
    return [(label, stat(repo)) for label, stat in STATS]


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    db_url = get_db_url()
    print("Connecting to database...")
    engine = create_engine(db_url)
    _logger.info("Connected to database")

    repo = ArticleRepository(engine)
    stats = compute_stats(repo)

    print("Article statistics")
    print("-------------------")
    for label, value in stats:
        print(f"{label}: {value}")


if __name__ == "__main__":
    main()
