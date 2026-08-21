"""
transform_news.py

Runs Phase 2 of the news pipeline — transforms — over articles already in the
database. Extraction (``load_news_articles.py``) and transformation are
deliberately separate: transforms can be re-run, or applied retroactively to
the full historical article set, without re-fetching anything.

Progress is recorded per article in ``transform_log``, so an interrupted run
resumes where it left off rather than rescoring from the start.

Configuration (via .env or environment):
  DATABASE_URL    - SQLAlchemy connection string (required)
  NEWS_LOG_LEVEL  - Logging verbosity (default: INFO)

Usage:
  python transform_news.py                          # all transforms, everything pending
  python transform_news.py --transform sentiment    # just sentiment
  python transform_news.py --max-articles 100       # smoke test on a small slice
  python transform_news.py --device cuda            # force GPU
"""

import argparse
import logging
import sys

from sqlalchemy import create_engine

from findata.sources.news.config import LOG_LEVEL, get_db_url
from findata.sources.news.pipeline import TransformationPipeline
from findata.sources.news.transformers.sentiment import SentimentTransformer

# ---------------------------------------------------------------------------
# Logging setup — suppress chatty third-party loggers that drown out our own
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

for _noisy in ("httpx", "httpcore", "urllib3", "transformers", "huggingface_hub", "filelock"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

_logger = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply transforms to news articles already in the database.",
    )
    parser.add_argument(
        "--transform",
        metavar="ID",
        help="Only run the transformer with this transform_id (e.g. 'sentiment')",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=TransformationPipeline.DEFAULT_BATCH_SIZE,
        metavar="N",
        help=(
            "Articles loaded and scored per iteration "
            f"(default: {TransformationPipeline.DEFAULT_BATCH_SIZE})"
        ),
    )
    parser.add_argument(
        "--model-batch-size",
        type=int,
        default=32,
        metavar="N",
        help="Articles per model forward pass (default: 32; raise on a GPU)",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        metavar="N",
        help="Stop after N articles per transformer (default: process everything)",
    )
    parser.add_argument(
        "--device",
        choices=("cpu", "cuda"),
        help="Force a device for the sentiment model (default: auto-detect)",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    db_url = get_db_url()
    engine = create_engine(db_url)
    _logger.info("Connected to database")

    transformers = [
        SentimentTransformer(
            batch_size=args.model_batch_size,
            device=args.device,
        ),
    ]

    if args.transform and not any(t.transform_id == args.transform for t in transformers):
        available = ", ".join(t.transform_id for t in transformers)
        print(
            f"Error: unknown transform '{args.transform}'. Available: {available}",
            file=sys.stderr,
        )
        sys.exit(1)

    processed = TransformationPipeline(engine, transformers=transformers).run(
        transform_name=args.transform,
        batch_size=args.batch_size,
        max_articles=args.max_articles,
    )
    _logger.info("Done — %d article(s) processed.", processed)


if __name__ == "__main__":
    main()
