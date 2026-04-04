"""
db/repository.py

Data access layer for the articles and article_tickers tables.

ArticleRepository handles all reads and writes so the rest of the codebase
never constructs raw SQL. This keeps query logic in one place and makes
the database easy to swap out (SQLite for local dev, PostgreSQL for prod).

Usage:
    from sqlalchemy import create_engine
    from news_articles.db.repository import ArticleRepository

    engine = create_engine(db_url)
    repo = ArticleRepository(engine)
    repo.create_tables()

    repo.insert_articles(articles)
    repo.link_tickers(article_id=1, tickers=["AAPL", "MSFT"])
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from .schema import article_tickers, articles, metadata

_logger = logging.getLogger(__name__)


class ArticleRepository:
    """Read/write access to the articles store."""

    def __init__(self, engine: Engine):
        self.engine = engine

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def create_tables(self) -> None:
        """Create all tables if they do not already exist."""
        metadata.create_all(self.engine)
        _logger.debug("Database tables are ready")

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def insert_articles(self, rows: list[dict]) -> int:
        """
        Insert a batch of articles, skipping any whose URL already exists.

        Each dict in `rows` should contain the article fields defined in
        schema.py (url, title, author, publisher, source, content,
        published_at). The fetched_at column is set automatically by the DB.

        Args:
            rows: List of article dicts to insert.

        Returns:
            Number of rows actually inserted (duplicates excluded).
        """
        if not rows:
            return 0

        new_urls = {r["url"] for r in rows}
        existing = self._existing_urls(new_urls)
        to_insert = [r for r in rows if r["url"] not in existing]

        if not to_insert:
            _logger.info("All %d articles already present — nothing to insert", len(rows))
            return 0

        with self.engine.begin() as conn:
            conn.execute(articles.insert(), to_insert)

        skipped = len(rows) - len(to_insert)
        _logger.info(
            "Inserted %d articles%s",
            len(to_insert),
            f" (skipped {skipped} duplicates)" if skipped else "",
        )
        return len(to_insert)

    def link_tickers(self, article_id: int, tickers: list[str]) -> None:
        """
        Associate a list of ticker symbols with an article.

        Called by the entity extraction transformer after it identifies
        company mentions in the article content.

        Args:
            article_id: The articles.id value.
            tickers:    Ticker symbols found in the article, e.g. ["AAPL", "MSFT"].
        """
        if not tickers:
            return

        rows = [{"article_id": article_id, "ticker": t} for t in tickers]
        with self.engine.begin() as conn:
            conn.execute(article_tickers.insert(), rows)
        _logger.debug("Linked %d tickers to article %d", len(tickers), article_id)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_untransformed(self, transform_name: str) -> list[dict]:
        """
        Return articles that have not yet had a given transform applied.

        This enables the transform step to be run independently of extraction —
        new transforms can be applied to the full historical article set.

        Args:
            transform_name: Identifier for the transform, e.g. "sentiment".

        Returns:
            List of article dicts with keys matching the articles table columns.

        TODO: Implement a transform_log table to track which transforms have
              been applied to which articles. For now, returns all articles.
        """
        _logger.warning(
            "get_untransformed('%s') is not yet implemented — returning all articles",
            transform_name,
        )
        return self.get_all()

    def get_all(self) -> list[dict]:
        """Return every article as a list of dicts."""
        with self.engine.connect() as conn:
            result = conn.execute(select(articles))
            return [dict(row._mapping) for row in result]

    def get_by_ticker(self, ticker: str) -> list[dict]:
        """
        Return all articles linked to a given ticker symbol.

        Requires that entity extraction has already been run to populate
        the article_tickers table.

        Args:
            ticker: Ticker symbol, e.g. "AAPL".

        Returns:
            List of article dicts.
        """
        stmt = (
            select(articles)
            .join(article_tickers, articles.c.id == article_tickers.c.article_id)
            .where(article_tickers.c.ticker == ticker)
            .order_by(articles.c.published_at.desc())
        )
        with self.engine.connect() as conn:
            result = conn.execute(stmt)
            return [dict(row._mapping) for row in result]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _existing_urls(self, urls: set[str]) -> set[str]:
        """Return the subset of `urls` that already exist in the database."""
        stmt = select(articles.c.url).where(articles.c.url.in_(urls))
        with self.engine.connect() as conn:
            result = conn.execute(stmt)
            return {row[0] for row in result}
