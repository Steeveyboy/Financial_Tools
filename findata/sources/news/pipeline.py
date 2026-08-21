"""
pipeline.py

Orchestrates the two-phase ETL pipeline for news articles.

Phase 1 — Extraction (run on a schedule, e.g. every hour):
    ExtractionPipeline fetches articles from all registered extractors
    and loads them into the database. No transforms are applied here.

Phase 2 — Transformation (run separately, can be re-run at any time):
    TransformationPipeline loads unprocessed articles from the database
    and applies each registered transformer in order.

Usage:
    from sqlalchemy import create_engine
    from findata.sources.news.pipeline import ExtractionPipeline, TransformationPipeline
    from findata.sources.news.extractors.rss import RSSExtractor
    from findata.sources.news.transformers.sentiment import SentimentTransformer
    from findata.sources.news.transformers.entity import EntityTransformer

    engine = create_engine(db_url)

    # --- Phase 1: extract and load ---
    extraction = ExtractionPipeline(engine, extractors=[
        RSSExtractor(feed_urls=["https://..."]),
    ])
    extraction.run()

    # --- Phase 2: transform (run separately) ---
    transformation = TransformationPipeline(engine, transformers=[
        SentimentTransformer(),
        EntityTransformer(),
    ])
    transformation.run()
"""

from __future__ import annotations

import logging

from sqlalchemy.engine import Engine

from .db.repository import ArticleRepository
from .extractors.base import ArticleExtractor
from .transformers.base import ArticleTransformer

import time

_logger = logging.getLogger(__name__)


class ExtractionPipeline:
    """
    Runs all extractors and loads their articles into the database.

    Extractors that implement extract_batches() are consumed incrementally
    so rows appear in the database as they stream — no need to wait for
    the full dataset to finish before seeing results.

    Args:
        engine:     SQLAlchemy engine connected to the target database.
        extractors: List of ArticleExtractor instances to run.
    """

    def __init__(self, engine: Engine, extractors: list[ArticleExtractor]):
        self.repo = ArticleRepository(engine)
        self.extractors = extractors

    def run(self) -> int:
        """
        Execute all extractors and persist the results.

        Returns:
            Total number of new articles inserted across all extractors.
        """
        self.repo.create_tables()
        total_inserted = 0

        for extractor in self.extractors:
            _logger.info("Running extractor: %s", extractor.source_id)
            inserted = self._run_extractor(extractor)
            total_inserted += inserted

        _logger.info("Extraction complete — %d new articles inserted", total_inserted)
        return total_inserted

    def _run_extractor(self, extractor: ArticleExtractor) -> int:
        """Run a single extractor, consuming batches incrementally."""
        inserted = 0

        for batch in extractor.extract_batches():
            start_time = time.time()
            batch = extractor._tag_source(batch)
            num_inserted = self.repo.insert_articles(batch)
            self._link_known_tickers(batch)
            _logger.info("Batch processed: %d articles (%.3f seconds)", len(batch), time.time() - start_time)
            inserted += num_inserted
            

        return inserted

    def _link_known_tickers(self, articles: list[dict]) -> None:
        """
        Link tickers to articles when the extractor already knows them.

        Batches all ID lookups and inserts into two queries per batch
        rather than 2×N individual queries, which is critical for the
        FNSPID dataset with millions of rows.
        """
        articles_with_tickers = [a for a in articles if a.get("mentioned_tickers")]
        if not articles_with_tickers:
            return

        # Fetch all article IDs for this batch in a single query.
        urls = [a["url"] for a in articles_with_tickers]
        url_to_id = self.repo.get_ids_by_urls(urls)

        # Build all ticker link rows and insert in one operation.
        links = []
        for article in articles_with_tickers:
            article_id = url_to_id.get(article["url"])
            if article_id is None:
                continue  # duplicate URL, not inserted
            for ticker in article["mentioned_tickers"]:
                links.append({"article_id": article_id, "ticker": ticker})

        self.repo.bulk_link_tickers(links)


class TransformationPipeline:
    """
    Applies a sequence of transformers to articles already in the database.

    Transformers are applied in the order they are registered. Each transformer
    receives the output of the previous one, allowing them to build on each
    other (e.g. entity extraction can use sentiment scores if needed).

    Args:
        engine:       SQLAlchemy engine connected to the target database.
        transformers: Ordered list of ArticleTransformer instances to apply.
    """

    #: Articles loaded from the database per transform iteration. Bounds peak
    #: memory and, because each batch is logged to transform_log before the
    #: next is fetched, caps how much work an interrupted run loses.
    DEFAULT_BATCH_SIZE = 500

    def __init__(self, engine: Engine, transformers: list[ArticleTransformer]):
        self.repo = ArticleRepository(engine)
        self.transformers = transformers

    def run(
        self,
        transform_name: str | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_articles: int | None = None,
    ) -> int:
        """
        Apply all (or one) transformer(s) to unprocessed articles.

        Each transformer pages through the articles it hasn't seen, in batches,
        persisting and logging each batch before fetching the next. A run that
        is interrupted resumes where it stopped — nothing already logged to
        ``transform_log`` is rescored.

        Args:
            transform_name: If provided, only run the transformer with this
                            transform_id. Useful for re-running a single step.
            batch_size:     Articles loaded and scored per iteration.
            max_articles:   Stop after processing this many articles per
                            transformer. Useful for smoke tests against a
                            large table; ``None`` processes everything.

        Returns:
            Total number of articles processed across all transformers.
        """
        targets = self.transformers
        if transform_name:
            targets = [t for t in self.transformers if t.transform_id == transform_name]
            if not targets:
                _logger.error("No transformer found with id '%s'", transform_name)
                return 0

        total = 0
        for transformer in targets:
            total += self._run_transformer(transformer, batch_size, max_articles)
        return total

    def _run_transformer(
        self,
        transformer: ArticleTransformer,
        batch_size: int,
        max_articles: int | None,
    ) -> int:
        """Page a single transformer over its untransformed articles."""
        tid = transformer.transform_id
        remaining = self.repo.count_untransformed(tid)
        _logger.info("Running transformer '%s' — %d article(s) pending", tid, remaining)

        processed = 0
        while True:
            if max_articles is not None:
                if processed >= max_articles:
                    break
                batch_size = min(batch_size, max_articles - processed)

            articles = self.repo.get_untransformed(tid, limit=batch_size)
            if not articles:
                break

            start = time.time()
            try:
                enriched = transformer.transform(articles)
                self._persist(transformer, enriched)
            except Exception as exc:
                # Deliberately not logged to transform_log: an unhandled
                # failure means we don't know what was applied, so the batch
                # stays pending and the next run retries it.
                _logger.error(
                    "Transformer '%s' failed on batch of %d: %s",
                    tid,
                    len(articles),
                    exc,
                    exc_info=True,
                )
                return processed

            self.repo.mark_transformed([a["id"] for a in articles], tid)

            processed += len(articles)
            _logger.info(
                "'%s' — %d/%d articles (%.2fs for this batch)",
                tid,
                processed,
                remaining,
                time.time() - start,
            )

            # A short final batch means the pending set is exhausted.
            if len(articles) < batch_size:
                break

        _logger.info("Transformer '%s' complete — %d article(s) processed", tid, processed)
        return processed

    def _persist(self, transformer: ArticleTransformer, articles: list[dict]) -> None:
        """
        Write transformer results back to the database.

        Each transformer produces different output fields, so persistence
        logic is handled per transform_id.

        Callers must not log articles to ``transform_log`` here — the caller
        does that only after this method returns cleanly, so a failed write
        leaves the batch pending for the next run.

        TODO: As transformers are implemented, add a branch here for each
              transform_id to persist its specific output fields.
        """
        if transformer.transform_id == "entity_extraction":
            for article in articles:
                tickers = article.get("mentioned_tickers", [])
                if tickers:
                    self.repo.link_tickers(article["id"], tickers)

        elif transformer.transform_id == "sentiment":
            # A None score is written as NULL on purpose: the article had no
            # usable text. transform_log is what marks it as already seen.
            self.repo.update_sentiment_scores(
                [
                    {"id": a["id"], "sentiment_score": a.get("sentiment_score")}
                    for a in articles
                ]
            )

        _logger.debug(
            "Persisted results for transformer '%s' (%d articles)",
            transformer.transform_id,
            len(articles),
        )
