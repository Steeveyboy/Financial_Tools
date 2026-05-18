"""
db/repository.py

Data access layer for the ``articles`` and ``article_tickers`` tables.

Backed by the ORM models in :mod:`findata.models` and SQLAlchemy 2.0 sessions
from :mod:`findata.db.session`. Callers never construct raw SQL; the rest of
the codebase only talks to :class:`ArticleRepository`.

Usage:

    # Default — use findata's configured engine (DATABASE_URL):
    from findata.sources.news.db.repository import ArticleRepository
    repo = ArticleRepository()

    # Or inject an engine (tests, ad-hoc SQLite):
    from sqlalchemy import create_engine
    repo = ArticleRepository(create_engine("sqlite:///:memory:"))

    repo.create_tables()
    repo.insert_articles(rows)
    repo.link_tickers(article_id=1, tickers=["AAPL", "MSFT"])

Reads return plain ``dict`` rows — the same shape the extraction/transform
pipeline already consumes (``a["url"]``, ``a["id"]`` etc.). Internally the
methods drive the ORM ``Article`` / ``ArticleTicker`` mappers.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from findata.db.session import get_engine
from findata.models import Article, ArticleTicker, Base

_logger = logging.getLogger(__name__)

# Valid column names for the articles table — used to strip extra keys
# (e.g. 'mentioned_tickers') before issuing INSERT statements.
_ARTICLE_COLUMNS: frozenset[str] = frozenset(
    c.name for c in Article.__table__.c
)


def _article_to_dict(a: Article) -> dict[str, Any]:
    """Project an :class:`Article` ORM row to the dict shape callers expect."""
    return {
        "id": a.id,
        "url": a.url,
        "title": a.title,
        "author": a.author,
        "publisher": a.publisher,
        "source": a.source,
        "content": a.content,
        "published_at": a.published_at,
        "fetched_at": a.fetched_at,
    }


class ArticleRepository:
    """Read/write access to the news article store."""

    def __init__(self, engine: Engine | None = None):
        """Build a repository against *engine* (or findata's default)."""
        self.engine: Engine = engine if engine is not None else get_engine()
        self._SessionFactory: sessionmaker = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    # ------------------------------------------------------------------
    # Session helper
    # ------------------------------------------------------------------

    def _session(self) -> Session:
        """Return a fresh ORM session bound to this repository's engine."""
        return self._SessionFactory()

    def _article_ticker_insert_stmt(self):
        """Return a dialect-aware ``INSERT ... ON CONFLICT DO NOTHING`` for
        :class:`ArticleTicker`, falling back to a plain insert on dialects
        that don't support upsert. Lets transforms be re-run safely without
        violating the ``(article_id, ticker)`` primary key.
        """
        dialect = self.engine.dialect.name
        if dialect == "postgresql":
            return pg_insert(ArticleTicker).on_conflict_do_nothing()
        if dialect == "sqlite":
            return sqlite_insert(ArticleTicker).on_conflict_do_nothing()
        return insert(ArticleTicker)

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def create_tables(self) -> None:
        """Create the news tables if they do not already exist (dev convenience).

        In production use ``alembic upgrade head`` instead.
        """
        Base.metadata.create_all(
            self.engine,
            tables=[Article.__table__, ArticleTicker.__table__],
        )
        _logger.debug("Database tables are ready")

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def insert_articles(self, rows: list[dict]) -> int:
        """Insert a batch of articles, skipping any whose URL already exists.

        Each dict in *rows* should contain the article fields defined on the
        :class:`Article` model. ``fetched_at`` is set automatically by the
        database via its ``server_default``.

        Args:
            rows: List of article dicts to insert.

        Returns:
            Number of rows actually inserted (duplicates excluded).
        """
        if not rows:
            return 0

        existing = self._existing_urls({r["url"] for r in rows})

        # Deduplicate within the batch itself — FNSPID has the same URL
        # under multiple tickers, producing duplicate rows in one batch.
        seen: set[str] = set()
        to_insert: list[dict] = []
        for r in rows:
            if r["url"] not in existing and r["url"] not in seen:
                seen.add(r["url"])
                to_insert.append(r)

        if not to_insert:
            _logger.info(
                "All %d articles already present — nothing to insert", len(rows)
            )
            return 0

        # Strip keys that aren't table columns (e.g. 'mentioned_tickers') so
        # the bulk INSERT compiler doesn't complain about unknown columns.
        clean_rows = [
            {k: v for k, v in r.items() if k in _ARTICLE_COLUMNS}
            for r in to_insert
        ]

        with self._session() as session:
            session.execute(insert(Article), clean_rows)
            session.commit()

        skipped = len(rows) - len(to_insert)
        _logger.info(
            "Inserted %d articles%s",
            len(to_insert),
            f" (skipped {skipped} duplicates)" if skipped else "",
        )
        return len(to_insert)

    def link_tickers(self, article_id: int, tickers: list[str]) -> None:
        """Associate a list of ticker symbols with an article.

        Called by the entity-extraction transformer after it identifies
        company mentions in the article content.

        Args:
            article_id: The ``articles.id`` value.
            tickers:    Ticker symbols found in the article (e.g. ``["AAPL"]``).
        """
        if not tickers:
            return

        # Dedupe — the composite PK (article_id, ticker) forbids duplicates.
        unique = sorted(set(tickers))
        rows = [{"article_id": article_id, "ticker": t} for t in unique]

        with self._session() as session:
            session.execute(self._article_ticker_insert_stmt(), rows)
            session.commit()
        _logger.debug("Linked %d tickers to article %d", len(unique), article_id)

    def bulk_link_tickers(self, links: list[dict]) -> None:
        """Insert many ``(article_id, ticker)`` pairs in one operation.

        More efficient than :meth:`link_tickers` per article when processing
        a batch of articles with known tickers.

        Args:
            links: List of dicts with keys ``article_id`` and ``ticker``.
        """
        if not links:
            return

        # Dedupe within the batch — composite PK forbids duplicates.
        seen: set[tuple[int, str]] = set()
        unique: list[dict] = []
        for link in links:
            key = (link["article_id"], link["ticker"])
            if key not in seen:
                seen.add(key)
                unique.append(link)

        with self._session() as session:
            session.execute(self._article_ticker_insert_stmt(), unique)
            session.commit()
        _logger.debug("Bulk linked %d ticker associations", len(unique))

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_untransformed(self, transform_name: str) -> list[dict]:
        """Return articles that have not yet had a given transform applied.

        This enables the transform step to be run independently of extraction —
        new transforms can be applied to the full historical article set.

        Args:
            transform_name: Identifier for the transform, e.g. ``"sentiment"``.

        Returns:
            List of article dicts.

        TODO: Implement a ``transform_log`` table to track which transforms
              have been applied to which articles. For now, returns all.
        """
        _logger.warning(
            "get_untransformed('%s') is not yet implemented — returning all articles",
            transform_name,
        )
        return self.get_all()

    def get_all(self) -> list[dict]:
        """Return every article as a list of dicts."""
        stmt = select(Article)
        with self._session() as session:
            return [_article_to_dict(a) for a in session.execute(stmt).scalars()]

    def iter_all(self, batch_size: int = 1000) -> Iterator[dict]:
        """Stream every article as dicts, ``batch_size`` rows per chunk.

        Use this in transforms that operate over the full table — avoids
        loading 1.9M rows into memory at once.
        """
        stmt = select(Article).execution_options(yield_per=batch_size)
        with self._session() as session:
            for article in session.execute(stmt).scalars():
                yield _article_to_dict(article)

    def get_by_ticker(self, ticker: str) -> list[dict]:
        """Return all articles linked to a given ticker, newest first.

        Requires entity extraction to have populated ``article_tickers``.
        """
        stmt = (
            select(Article)
            .join(ArticleTicker, Article.id == ArticleTicker.article_id)
            .where(ArticleTicker.ticker == ticker)
            .order_by(Article.published_at.desc())
        )
        with self._session() as session:
            return [_article_to_dict(a) for a in session.execute(stmt).scalars()]

    # ------------------------------------------------------------------
    # ID lookups
    # ------------------------------------------------------------------

    def get_ids_by_urls(self, urls: list[str]) -> dict[str, int]:
        """Return a ``{url: article_id}`` mapping for *urls* in one query.

        Used by the pipeline to batch-resolve IDs after inserting a batch,
        avoiding per-article SELECTs.
        """
        if not urls:
            return {}
        stmt = select(Article.id, Article.url).where(Article.url.in_(urls))
        with self._session() as session:
            return {url: aid for aid, url in session.execute(stmt)}

    def get_id_by_url(self, url: str) -> int | None:
        """Return the ``articles.id`` for *url*, or ``None`` if not found."""
        stmt = select(Article.id).where(Article.url == url)
        with self._session() as session:
            return session.execute(stmt).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _existing_urls(self, urls: set[str]) -> set[str]:
        """Return the subset of *urls* that already exist in the database."""
        if not urls:
            return set()
        stmt = select(Article.url).where(Article.url.in_(urls))
        with self._session() as session:
            return set(session.execute(stmt).scalars())
