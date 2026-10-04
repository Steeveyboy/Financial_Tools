"""
load_dojo_stock_news.py

Loads the AlphaDojo/dojo_stock_news HuggingFace dataset, as-is, into the
``news.dojo_stock_news`` staging table. Each run replaces the table's contents.

A separate transform (not yet written) normalizes staging rows into
``news.articles`` / ``news.article_securities``.

Configuration (via .env or environment):
  DATABASE_URL    - SQLAlchemy connection string (required)
  NEWS_LOG_LEVEL  - Logging verbosity (default: INFO)

Usage:
  python load_dojo_stock_news.py
  python load_dojo_stock_news.py --limit 1000
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
        help="Load only the first N rows (default: all)",
    )
    args = parser.parse_args()

    loaded = load_dojo_stock_news(batch_size=args.batch_size, limit=args.limit)
    _logger.info("Done — %d row(s) in dojo_stock_news.", loaded)


if __name__ == "__main__":
    main()
