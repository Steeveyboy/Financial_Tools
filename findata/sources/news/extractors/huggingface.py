"""
extractors/huggingface.py

HuggingFace dataset extractor for Zihan1004/FNSPID.

FNSPID (Financial News and Stock Price Integration Dataset) contains
~15.7 million financial news records spanning 1999–2023 across 4,775
S&P 500 companies. Loading the full dataset at once is impractical, so
this extractor uses HuggingFace's streaming mode and yields articles in
batches to keep memory usage constant regardless of dataset size.

Dataset schema (populated columns only):
    Date          - Publication timestamp (string, UTC)
    Article_title - Headline text
    Stock_symbol  - Ticker symbol the article is associated with
    Url           - Canonical article URL (used for deduplication)
    Publisher     - Outlet name

Usage:
    from findata.sources.news.extractors.huggingface import FNSPIDExtractor

    extractor = FNSPIDExtractor(
        tickers=["AAPL", "MSFT", "NVDA"],
        start_date="2020-01-01",
        end_date="2023-12-31",
    )

    # Preferred — inserts in chunks as they stream:
    for batch in extractor.extract_batches():
        repo.insert_articles(batch)
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime

from findata.db.types import ensure_utc
import time
from tqdm import tqdm

from .base import ArticleExtractor

_logger = logging.getLogger(__name__)

DATASET_NAME = "Zihan1004/FNSPID"

_DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S%z",   # ISO 8601 with T separator
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
]


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse FNSPID's date string to an **aware** UTC datetime.

    FNSPID publishes no offset, so the value is taken as UTC — see
    :func:`findata.db.types.ensure_utc`. Returns ``None`` for anything
    unparseable; the repository drops undated articles at insert time.
    """
    if not date_str:
        return None
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return ensure_utc(dt)
        except ValueError:
            continue
    _logger.debug("Could not parse FNSPID date: %r", date_str)
    return None


class FNSPIDExtractor(ArticleExtractor):
    """
    Streams articles from the Zihan1004/FNSPID HuggingFace dataset.

    Args:
        tickers:    Filter by ticker symbols. None means all tickers.
        start_date: YYYY-MM-DD inclusive lower bound. None means no bound.
        end_date:   YYYY-MM-DD inclusive upper bound. None means no bound.
        split:      HuggingFace dataset split (default: "train").
        batch_size: Articles per batch yielded by extract_batches().
    """

    ingest_source = "fnspid"

    def __init__(
        self,
        tickers: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        split: str = "train",
        batch_size: int = 500,
    ):
        self.ticker_filter: set[str] | None = set(tickers) if tickers else None
        # Both bounds MUST be aware: they are compared against `published_at`,
        # which _parse_date() returns as aware UTC. A bare strptime() here is
        # naive, and the comparison in _in_date_range() then raises
        # "can't compare offset-naive and offset-aware datetimes" — the whole of
        # REPO_REVIEW #3.
        self.start_date = (
            ensure_utc(datetime.strptime(start_date, "%Y-%m-%d")) if start_date else None
        )
        self.end_date = (
            ensure_utc(datetime.strptime(end_date, "%Y-%m-%d")) if end_date else None
        )
        self.split = split
        self.batch_size = batch_size

    def extract(self) -> list[dict]:
        """
        Return all matching articles as a single list.

        Prefer extract_batches() for large datasets.
        """
        all_articles = []
        for batch in self.extract_batches():
            all_articles.extend(batch)
        return all_articles

    def extract_batches(self) -> Iterator[list[dict]]:
        """
        Stream FNSPID and yield articles in batches of `batch_size`.

        Memory usage stays proportional to batch_size, not dataset size.
        A tqdm progress bar displays scan rate and kept/skipped counts.
        """
        from datasets import load_dataset

        _logger.info(
            "Streaming FNSPID (tickers=%s, start=%s, end=%s, batch_size=%d)",
            list(self.ticker_filter) if self.ticker_filter else "all",
            self.start_date.date() if self.start_date else "none",
            self.end_date.date()   if self.end_date   else "none",
            self.batch_size,
        )

        dataset = load_dataset(DATASET_NAME, split=self.split, streaming=False)

        batch: list[dict] = []
        kept = 0
        skipped = 0

        progress = tqdm(
            dataset,
            desc="FNSPID",
            unit=" rows",
            bar_format="{desc}: {n_fmt} scanned | {rate_fmt} | kept {postfix[kept]} | skipped {postfix[skipped]}",
            postfix={"kept": 0, "skipped": 0},
        )

        start_time = time.time()
        # Iterate `progress`, not `dataset`: tqdm only advances the bar for rows
        # drawn through it. Wrapping the dataset and then looping over the
        # original meant the bar rendered nothing at all.
        for row in progress:
            article = self._normalise(row)
            if article is None or not self._passes_filters(article):
                skipped += 1
                progress.postfix["skipped"] = skipped
                continue

            batch.append(article)
            kept += 1

            if len(batch) >= self.batch_size:
                progress.postfix["kept"] = kept
                progress.postfix["skipped"] = skipped
                _logger.info("Batch ready: %d articles (%.3f seconds)", len(batch), time.time() - start_time)
                yield batch
                start_time = time.time()
                batch = []

        if batch:
            yield batch

        _logger.info("FNSPID complete: %d kept, %d skipped", kept, skipped)

    def _normalise(self, row: dict) -> dict | None:
        """Map a raw FNSPID row to the articles table schema."""
        url = row.get("Url")
        if not url:
            return None

        ticker = row.get("Stock_symbol")
        
        published_date =  row.get("Date", "").replace(" UTC", "")
        
        return {
            "url":               url,
            "title":             row.get("Article_title"),
            "author":            row.get("Author"),
            "publisher":         row.get("Publisher"),
            "content":           row.get("Article", None),
            "published_at":      _parse_date(published_date),
            "mentioned_symbols": [ticker] if ticker else [],
        }

    def _passes_filters(self, article: dict) -> bool:
        """Return True if the article satisfies all active filters."""
        if self.ticker_filter:
            tickers = article.get("mentioned_symbols", [])
            if not any(t in self.ticker_filter for t in tickers):
                return False

        pub_date = article.get("published_at")
        if pub_date:
            if self.start_date and pub_date < self.start_date:
                return False
            if self.end_date and pub_date > self.end_date:
                return False

        return True
