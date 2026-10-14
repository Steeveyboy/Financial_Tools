"""
load_dojo_stock_news.py

Loads the AlphaDojo/dojo_stock_news HuggingFace dataset, as-is, into the
``news.dojo_stock_news`` staging table. Each run appends the rows that are not
staged yet (by ``url`` + ``page_symbol``); ``--replace`` clears the table first.

``load_news_articles.py --dojo`` then normalizes staging rows into
``news.articles`` / ``news.article_securities``.

Configuration (via .env or environment):
  DATABASE_URL    - SQLAlchemy connection string (required)
  NEWS_LOG_LEVEL  - Logging verbosity (default: INFO)

Usage:
  python load_dojo_stock_news.py
  python load_dojo_stock_news.py --limit 1000
  python load_dojo_stock_news.py --replace
"""

import argparse
import logging

from findata.sources.news.config import LOG_LEVEL
from findata.sources.news.staging.dojo import load_dojo_stock_news

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

for _noisy in ("httpx", "httpcore", "urllib3", "datasets", "huggingface_hub", "fsspec"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

_logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load AlphaDojo/dojo_stock_news into the dojo_stock_news staging table.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=5000, metavar="N",
        help="Rows per database insert batch (default: 5000)",
    )
    parser.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="Read only the first N rows (default: all)",
    )
    parser.add_argument(
        "--replace", action="store_true",
        help="Clear the staging table before loading (default: append new rows)",
    )
    args = parser.parse_args()

    appended = load_dojo_stock_news(
        batch_size=args.batch_size, limit=args.limit, replace=args.replace,
    )
    _logger.info("Done — %d new row(s) appended to dojo_stock_news.", appended)


if __name__ == "__main__":
    main()
