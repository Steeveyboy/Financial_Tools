"""
extractors/huggingface.py

HuggingFace dataset extractor for Zihan1004/FNSPID.

FNSPID (Financial News and Stock Price Integration Dataset) contains
~15.7 million financial news records spanning 1999–2023 across 4,775
S&P 500 companies. Loading the full dataset at once is impractical, so
this extractor uses HuggingFace's streaming mode to iterate row by row
without loading everything into memory.

Dataset schema (populated columns only):
    Date          - Publication timestamp (string, UTC)
    Article_title - Headline text
    Stock_symbol  - Ticker symbol the article is associated with
    Url           - Canonical article URL (used for deduplication)
    Publisher     - Outlet name

Note: The Article (full content) and Author columns exist in the schema
but are not populated in the current dataset release. Content will be
stored as None until a version with full text becomes available.

A key advantage of FNSPID: because Stock_symbol is provided directly,
entity extraction is not needed for this source. The extractor attaches
`mentioned_tickers` to each article dict and the pipeline links them
at load time, bypassing the EntityTransformer for these records.

Usage:
    from news_articles.extractors.huggingface import FNSPIDExtractor

    # Load a specific set of tickers within a date range
    extractor = FNSPIDExtractor(
        tickers=["AAPL", "MSFT", "NVDA"],
        start_date="2020-01-01",
        end_date="2023-12-31",
    )
    articles = extractor.extract()

    # Load everything (slow — 15.7M rows)
    extractor = FNSPIDExtractor()
    articles = extractor.extract()
"""

from __future__ import annotations

import logging
from datetime import datetime

from datasets import load_dataset

from .base import ArticleExtractor

_logger = logging.getLogger(__name__)

DATASET_NAME = "Zihan1004/FNSPID"

# FNSPID date format: e.g. "2020-01-15 09:30:00+00:00"
_DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
]


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse FNSPID's date string to a naive UTC datetime."""
    if not date_str:
        return None
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.replace(tzinfo=None)   # store as naive UTC
        except ValueError:
            continue
    _logger.debug("Could not parse FNSPID date: %r", date_str)
    return None


class FNSPIDExtractor(ArticleExtractor):
    """
    Streams articles from the Zihan1004/FNSPID HuggingFace dataset.

    Supports optional filtering by ticker and date range to avoid
    processing all 15.7 million rows on every run.

    Args:
        tickers:    If provided, only return articles whose Stock_symbol
                    is in this list. None means all tickers.
        start_date: Only include articles published on or after this date
                    (YYYY-MM-DD string). None means no lower bound.
        end_date:   Only include articles published on or before this date
                    (YYYY-MM-DD string). None means no upper bound.
        split:      HuggingFace dataset split to load (default: "train").
    """

    source_id = "huggingface_fnspid"

    def __init__(
        self,
        tickers: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        split: str = "train",
    ):
        self.ticker_filter: set[str] | None = set(tickers) if tickers else None
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        self.end_date   = datetime.strptime(end_date,   "%Y-%m-%d") if end_date   else None
        self.split = split

    def extract(self) -> list[dict]:
        """
        Stream FNSPID and return filtered, normalised article dicts.

        Each dict contains: url, title, publisher, published_at, content,
        and mentioned_tickers (populated from Stock_symbol). Author and
        content are None as they are not available in this dataset release.

        Returns:
            List of article dicts passing all active filters.
        """
        _logger.info(
            "Streaming FNSPID (tickers=%s, start=%s, end=%s)",
            list(self.ticker_filter) if self.ticker_filter else "all",
            self.start_date.date() if self.start_date else "none",
            self.end_date.date()   if self.end_date   else "none",
        )

        dataset = load_dataset(DATASET_NAME, split=self.split, streaming=True)

        articles: list[dict] = []
        processed = 0
        skipped = 0

        for row in dataset:
            processed += 1

            article = self._normalise(row)
            if article is None:
                skipped += 1
                continue

            if not self._passes_filters(article):
                skipped += 1
                continue

            articles.append(article)

            if processed % 100_000 == 0:
                _logger.info(
                    "FNSPID progress: %d rows processed, %d kept, %d skipped",
                    processed, len(articles), skipped,
                )

        _logger.info(
            "FNSPID extraction complete: %d articles kept from %d rows",
            len(articles), processed,
        )
        return articles

    def _normalise(self, row: dict) -> dict | None:
        """
        Map a raw FNSPID row to the articles table schema.

        Returns None for rows with no URL (cannot dedup without it).
        """
        url = row.get("Url")
        if not url:
            return None

        ticker = row.get("Stock_symbol")

        return {
            "url":               url,
            "title":             row.get("Article_title"),
            "author":            None,   # not populated in this dataset release
            "publisher":         row.get("Publisher"),
            "content":           None,   # not populated in this dataset release
            "published_at":      _parse_date(row.get("Date")),
            # Stock_symbol is provided directly — no entity extraction needed.
            # The pipeline reads this field and calls repo.link_tickers().
            "mentioned_tickers": [ticker] if ticker else [],
        }

    def _passes_filters(self, article: dict) -> bool:
        """Return True if the article satisfies all active filters."""
        if self.ticker_filter:
            tickers = article.get("mentioned_tickers", [])
            if not any(t in self.ticker_filter for t in tickers):
                return False

        pub_date = article.get("published_at")
        if pub_date:
            if self.start_date and pub_date < self.start_date:
                return False
            if self.end_date and pub_date > self.end_date:
                return False

        return True
