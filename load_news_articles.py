"""
load_news_articles.py

Runs the news articles extraction pipeline against the configured database.

Sources:
  - Reuters Business RSS feed (live articles)
  - FNSPID HuggingFace dataset (historical, filtered by ticker + date range)

Configuration (via .env or environment):
  DATABASE_URL    - SQLAlchemy connection string (required)
  NEWS_LOG_LEVEL  - Logging verbosity (default: INFO)

Usage:
  python load_news_articles.py
  python load_news_articles.py --fnspid --tickers AAPL MSFT --start-date 2020-01-01
"""

import argparse
import logging
import sys

from sqlalchemy import create_engine

from news_articles.config import LOG_LEVEL, get_db_url
from news_articles.extractors.huggingface import FNSPIDExtractor
from news_articles.extractors.rss import RSSExtractor
from news_articles.pipeline import ExtractionPipeline

# ---------------------------------------------------------------------------
# Logging setup — suppress chatty third-party loggers that drown out our own
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

for _noisy in ("httpx", "httpcore", "urllib3", "datasets", "huggingface_hub", "fsspec"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

_logger = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load financial news articles into the Resonance Desk database.",
    )
    parser.add_argument(
        "--rss",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run the Reuters Business RSS extractor (default: on)",
    )
    parser.add_argument(
        "--fnspid",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Run the FNSPID HuggingFace dataset extractor (default: off — slow)",
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        metavar="TICKER",
        help="Filter FNSPID to these ticker symbols, e.g. --tickers AAPL MSFT NVDA",
    )
    parser.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        help="FNSPID lower date bound (inclusive)",
    )
    parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        help="FNSPID upper date bound (inclusive)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        metavar="N",
        help="Articles per database insert batch (default: 500)",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    if not args.rss and not args.fnspid:
        print("Error: No extractors enabled. Pass --rss and/or --fnspid.", file=sys.stderr)
        sys.exit(1)

    db_url = get_db_url()
    engine = create_engine(db_url)
    _logger.info("Connected to database")

    extractors = []

    if args.rss:
        extractors.append(RSSExtractor())

    if args.fnspid:
        extractors.append(
            FNSPIDExtractor(
                tickers=args.tickers,
                start_date=args.start_date,
                end_date=args.end_date,
                batch_size=args.batch_size,
            )
        )

    inserted = ExtractionPipeline(engine, extractors=extractors).run()
    _logger.info("Done — %d new article(s) inserted.", inserted)


if __name__ == "__main__":
    main()
