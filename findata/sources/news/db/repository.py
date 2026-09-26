"""
db/repository.py

Data access layer for the ``news`` schema — ``articles``,
``article_securities`` and ``article_transforms``.

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
    repo.link_symbols(article_id=1, symbols=["AAPL", "MSFT"])

Reads return plain ``dict`` rows — the same shape the extraction/transform
pipeline already consumes (``a["url"]``, ``a["id"]`` etc.). Internally the
methods drive the ORM ``Article`` / ``ArticleSecurity`` mappers.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Iterator

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from findata.db.base import schema_translate_map_for
from findata.db.session import create_schemas, get_engine
from findata.db.types import ensure_utc
from findata.models import Article, ArticleSecurity, ArticleTransform, Base

_logger = logging.getLogger(__name__)

# Valid column names for the articles table — used to strip extra keys
# (e.g. 'mentioned_symbols') before issuing INSERT statements.
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
        "ingest_source": a.ingest_source,
        "content": a.content,
        "published_at": a.published_at,
        "created_at": a.created_at,
        "sentiment_score": a.sentiment_score,
    }


class ArticleRepository:
    """Read/write access to the news article store."""

    def __init__(self, engine: Engine | None = None):
        """Build a repository against *engine* (or findata's default).

        An injected engine gets the schema translate map applied here, so a
        caller can hand over a plain ``create_engine("sqlite://")`` without
        knowing that the models declare schemas. ``get_engine()`` has already
        done this for the default engine; re-applying is harmless.
        """
        engine = engine if engine is not None else get_engine()
        translate_map = schema_translate_map_for(engine.dialect.name)
        if translate_map:
            engine = engine.execution_options(schema_translate_map=translate_map)
        self.engine: Engine = engine
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

    def _article_transform_insert_stmt(self):
        """Return a dialect-aware ``INSERT ... ON CONFLICT DO NOTHING`` for
        :class:`ArticleTransform`, falling back to a plain insert on dialects
        that don't support upsert. Lets a partially-failed transform batch be
        re-run without violating the ``(article_id, transform_name)`` key.
        """
        dialect = self.engine.dialect.name
        if dialect == "postgresql":
            return pg_insert(ArticleTransform).on_conflict_do_nothing()
        if dialect == "sqlite":
            return sqlite_insert(ArticleTransform).on_conflict_do_nothing()
        return insert(ArticleTransform)

    def _article_security_insert_stmt(self):
        """Return a dialect-aware ``INSERT ... ON CONFLICT DO NOTHING`` for
        :class:`ArticleSecurity`, falling back to a plain insert on dialects
        that don't support upsert. Lets transforms be re-run safely without
        violating the ``(article_id, symbol)`` primary key.
        """
        dialect = self.engine.dialect.name
        if dialect == "postgresql":
            return pg_insert(ArticleSecurity).on_conflict_do_nothing()
        if dialect == "sqlite":
            return sqlite_insert(ArticleSecurity).on_conflict_do_nothing()
        return insert(ArticleSecurity)

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def create_tables(self) -> None:
        """Create the news tables if they do not already exist (dev convenience).

        In production use ``alembic upgrade head`` instead.
        """
        create_schemas(self.engine)
        Base.metadata.create_all(
            self.engine,
            tables=[
                Article.__table__,
                ArticleSecurity.__table__,
                ArticleTransform.__table__,
            ],
        )
        _logger.debug("Database tables are ready")

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def insert_articles(self, rows: list[dict]) -> int:
        """Insert a batch of articles, skipping any whose URL already exists.

        Each dict in *rows* should contain the article fields defined on the
        :class:`Article` model. ``created_at`` / ``updated_at`` are set by the
        database via their ``server_default``.

        Rows are filtered in three passes before insertion:

        1. **No ``published_at``** — dropped. The column is ``NOT NULL`` because
           an article with no timestamp cannot enter a time series, and
           extractors legitimately produce ``None`` for malformed feed entries.
           Filtering here rather than letting the INSERT raise is REPO_REVIEW #4.
        2. **URL already in the database** — skipped.
        3. **URL duplicated inside this batch** — skipped. FNSPID emits the same
           URL once per mentioned symbol.

        ``published_at`` is normalized to aware UTC on the way through; see
        :func:`findata.db.types.ensure_utc`.

        Args:
            rows: List of article dicts to insert.

        Returns:
            Number of rows actually inserted.
        """
        start_time = time.perf_counter()
        if not rows:
            return 0

        # Pass 1 — drop rows that cannot satisfy NOT NULL published_at.
        dated: list[dict] = []
        undated = 0
        for r in rows:
            if r.get("published_at") is None:
                undated += 1
                _logger.debug("Dropping article with no published_at: %s", r.get("url"))
                continue
            dated.append(r)

        if undated:
            _logger.warning(
                "Dropped %d of %d articles with no published_at "
                "(the column is NOT NULL — an undated article cannot be used)",
                undated,
                len(rows),
            )

        if not dated:
            return 0

        existing = self._existing_urls({r["url"] for r in dated})

        # Passes 2 and 3 — dedupe against the database and within the batch.
        seen: set[str] = set()
        to_insert: list[dict] = []
        for r in dated:
            if r["url"] not in existing and r["url"] not in seen:
                seen.add(r["url"])
                to_insert.append(r)

        if not to_insert:
            _logger.info(
                "All %d articles already present — nothing to insert", len(dated)
            )
            return 0

        # Strip keys that aren't table columns (e.g. 'mentioned_symbols') so the
        # bulk INSERT compiler doesn't complain, and normalize timestamps.
        clean_rows = []
        for r in to_insert:
            row = {k: v for k, v in r.items() if k in _ARTICLE_COLUMNS}
            row["published_at"] = ensure_utc(row["published_at"])
            clean_rows.append(row)

        with self._session() as session:
            session.execute(insert(Article), clean_rows)
            session.commit()

        duplicates = len(dated) - len(to_insert)
        _logger.info(
            "Inserted %d articles%s%s in %.3fs",
            len(to_insert),
            f" (skipped {duplicates} duplicates)" if duplicates else "",
            f" (dropped {undated} undated)" if undated else "",
            time.perf_counter() - start_time,
        )
        return len(to_insert)

    def link_symbols(
        self,
        article_id: int,
        symbols: list[str],
        link_source: str = "extractor",
    ) -> None:
        """Associate symbols with an article.

        Symbols are uppercased before insert — ``article_securities`` has a
        ``CHECK (symbol = upper(symbol))`` so that a string join to
        ``market.daily_bars`` or ``reference.companies`` cannot miss on case
        alone.

        Args:
            article_id:  The ``news.articles.id`` value.
            symbols:     Symbols mentioned in the article, e.g. ``["AAPL"]``.
            link_source: How the link was established — ``extractor`` when the
                         feed supplied it, ``entity_transform`` when it was
                         inferred from the text. The two have very different
                         precision, so the provenance is stored.
        """
        if not symbols:
            return

        # Dedupe — the composite PK (article_id, symbol) forbids duplicates.
        unique = sorted({s.strip().upper() for s in symbols if s and s.strip()})
        if not unique:
            return

        rows = [
            {"article_id": article_id, "symbol": s, "link_source": link_source}
            for s in unique
        ]

        with self._session() as session:
            session.execute(self._article_security_insert_stmt(), rows)
            session.commit()
        _logger.debug("Linked %d symbols to article %d", len(unique), article_id)

    def bulk_link_symbols(
        self, links: list[dict], link_source: str = "extractor"
    ) -> None:
        """Insert many ``(article_id, symbol)`` pairs in one operation.

        More efficient than :meth:`link_symbols` per article when processing a
        batch of articles with known symbols.

        Args:
            links:       Dicts with keys ``article_id`` and ``symbol``. A
                         per-row ``link_source`` overrides the argument.
            link_source: Default provenance for rows that don't carry one.
        """
        if not links:
            return

        # Dedupe within the batch — composite PK forbids duplicates.
        seen: set[tuple[int, str]] = set()
        unique: list[dict] = []
        for link in links:
            symbol = (link.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            key = (link["article_id"], symbol)
            if key in seen:
                continue
            seen.add(key)
            unique.append(
                {
                    "article_id": link["article_id"],
                    "symbol": symbol,
                    "link_source": link.get("link_source", link_source),
                }
            )

        if not unique:
            return

        with self._session() as session:
            session.execute(self._article_security_insert_stmt(), unique)
            session.commit()
        _logger.debug("Bulk linked %d symbol associations", len(unique))

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_untransformed(
        self, transform_name: str, limit: int | None = None
    ) -> list[dict]:
        """Return articles that have not yet had a given transform applied.

        This enables the transform step to be run independently of extraction —
        new transforms can be applied to the full historical article set.

        Implemented as an anti-join against ``news.article_transforms``: an article is
        "untransformed" when no ``(article_id, transform_name)`` row exists.
        Because the log records the *attempt*, articles that legitimately
        produced no result (empty content, model failure) are not retried on
        every run.

        Args:
            transform_name: Identifier for the transform, e.g. ``"sentiment"``.
            limit:          Maximum number of articles to return. Transforms
                            over the full FNSPID set should page through with
                            a limit rather than loading ~1.9M rows at once.

        Returns:
            List of article dicts, oldest first.
        """
        stmt = (
            select(Article)
            .outerjoin(
                ArticleTransform,
                (ArticleTransform.article_id == Article.id)
                & (ArticleTransform.transform_name == transform_name),
            )
            .where(ArticleTransform.article_id.is_(None))
            .order_by(Article.id)
        )
        if limit is not None:
            stmt = stmt.limit(limit)

        with self._session() as session:
            return [_article_to_dict(a) for a in session.execute(stmt).scalars()]

    def count_untransformed(self, transform_name: str) -> int:
        """Return how many articles still need *transform_name* applied."""
        stmt = (
            select(func.count())
            .select_from(Article)
            .outerjoin(
                ArticleTransform,
                (ArticleTransform.article_id == Article.id)
                & (ArticleTransform.transform_name == transform_name),
            )
            .where(ArticleTransform.article_id.is_(None))
        )
        with self._session() as session:
            return session.execute(stmt).scalar_one()

    def mark_transformed(self, article_ids: list[int], transform_name: str) -> None:
        """Record that *transform_name* has been applied to *article_ids*.

        Safe to call repeatedly — duplicate ``(article_id, transform_name)``
        pairs are ignored. Call this for every article the transform *saw*,
        including ones that produced no value, so they aren't reprocessed on
        the next run.

        Args:
            article_ids:    The ``articles.id`` values that were processed.
            transform_name: Identifier for the transform, e.g. ``"sentiment"``.
        """
        if not article_ids:
            return

        rows = [
            {"article_id": aid, "transform_name": transform_name}
            for aid in sorted(set(article_ids))
        ]
        with self._session() as session:
            session.execute(self._article_transform_insert_stmt(), rows)
            session.commit()
        _logger.debug(
            "Marked %d articles as transformed by '%s'", len(rows), transform_name
        )

    def update_sentiment_scores(self, scores: list[dict]) -> int:
        """Write ``sentiment_score`` values back to the ``articles`` table.

        Args:
            scores: List of dicts with keys ``id`` and ``sentiment_score``.
                    A ``None`` score is written as SQL ``NULL`` (the article
                    had no usable text); pair this with
                    :meth:`mark_transformed` so it isn't retried.

        Returns:
            Number of rows submitted for update.
        """
        if not scores:
            return 0

        # ORM "bulk UPDATE by primary key": each dict carries the primary key
        # plus the columns to set, and SQLAlchemy builds
        # `UPDATE articles SET sentiment_score=? WHERE id=?` as a single
        # executemany. Do NOT add an explicit .where() here — that turns it
        # into a bulk update with additional criteria, which the ORM session
        # refuses to synchronize.
        params = [
            {"id": s["id"], "sentiment_score": s.get("sentiment_score")}
            for s in scores
        ]

        with self._session() as session:
            session.execute(update(Article), params)
            session.commit()

        _logger.debug("Updated sentiment_score on %d articles", len(params))
        return len(params)

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

    def get_by_symbol(self, symbol: str) -> list[dict]:
        """Return all articles linked to a given symbol, newest first.

        Requires ``news.article_securities`` to have been populated, either by
        an extractor that supplied symbols or by the entity transform.
        """
        stmt = (
            select(Article)
            .join(ArticleSecurity, Article.id == ArticleSecurity.article_id)
            .where(ArticleSecurity.symbol == symbol.strip().upper())
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
    # Aggregate statistics
    # ------------------------------------------------------------------

    def count_articles(self) -> int:
        """Return the total number of rows in the ``articles`` table."""
        stmt = select(func.count()).select_from(Article)
        with self._session() as session:
            return session.execute(stmt).scalar_one()

    def count_unique_publishers(self) -> int:
        """Return the number of distinct non-null ``publisher`` values."""
        stmt = select(func.count(func.distinct(Article.publisher))).where(
            Article.publisher.isnot(None)
        )
        with self._session() as session:
            return session.execute(stmt).scalar_one()

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
