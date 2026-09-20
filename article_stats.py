"""
article_stats.py

Prints aggregate statistics about the articles table.

Configuration (via .env or environment):
  DATABASE_URL    - SQLAlchemy connection string (required)
  NEWS_LOG_LEVEL  - Logging verbosity (default: INFO)

Usage:
  python article_stats.py
"""

import logging

from sqlalchemy import create_engine

from news_articles.config import LOG_LEVEL, get_db_url
from news_articles.db.repository import ArticleRepository
from news_articles.stats import compute_stats

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_logger = logging.getLogger(__name__)


def main() -> None:
    engine = create_engine(get_db_url())
    repo = ArticleRepository(engine)

    stats = compute_stats(repo)

    print("Article statistics")
    print("-------------------")
    for label, value in stats:
        print(f"{label}: {value}")


if __name__ == "__main__":
    main()
