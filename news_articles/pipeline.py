"""
pipeline.py

Orchestrates the two-phase ETL pipeline for news articles.

Phase 1 — Extraction (run on a schedule, e.g. every hour):
    ExtractionPipeline fetches articles from all registered extractors
    and loads them into the database. No transforms are applied here.

Phase 2 — Transformation (run separately, can be re-run at any time):
    TransformationPipeline loads unprocessed articles from the database
    and applies each registered transformer in order.

Keeping these two phases separate means:
    - New transforms can be applied to the full historical dataset
    - Extraction can run frequently without triggering expensive transforms
    - Each transform can be re-run independently if it is improved

Usage:
    from sqlalchemy import create_engine
    from news_articles.pipeline import ExtractionPipeline, TransformationPipeline
    from news_articles.extractors.rss import RSSExtractor
    from news_articles.transformers.sentiment import SentimentTransformer
    from news_articles.transformers.entity import EntityTransformer

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

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from .db.repository import ArticleRepository
from .extractors.base import ArticleExtractor
from .transformers.base import ArticleTransformer

_logger = logging.getLogger(__name__)


class ExtractionPipeline:
    """
    Runs all extractors and loads their articles into the database.

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

        If an article dict contains a `mentioned_tickers` key (as provided
        by FNSPIDExtractor, which has Stock_symbol already), the tickers are
        linked to the article at load time — no EntityTransformer run needed
        for those records.

        Returns:
            Total number of new articles inserted across all extractors.
        """
        self.repo.create_tables()
        total_inserted = 0

        for extractor in self.extractors:
            _logger.info("Running extractor: %s", extractor.source_id)
            try:
                articles = extractor.extract()
                articles = extractor._tag_source(articles)
                inserted = self.repo.insert_articles(articles)
                total_inserted += inserted
                self._link_known_tickers(articles)
            except Exception as exc:
                _logger.error(
                    "Extractor '%s' failed: %s", extractor.source_id, exc
                )

        _logger.info("Extraction complete — %d new articles inserted", total_inserted)
        return total_inserted

    def _link_known_tickers(self, articles: list[dict]) -> None:
        """
        Link tickers to articles when the extractor already knows them.

        Some sources (e.g. FNSPID) provide a ticker symbol directly alongside
        each article. When `mentioned_tickers` is present in an article dict,
        we populate article_tickers at load time rather than waiting for the
        EntityTransformer to run later.
        """
        for article in articles:
            tickers = article.get("mentioned_tickers")
            if not tickers:
                continue

            # Look up the article's database ID by URL.
            article_id = self.repo.get_id_by_url(article["url"])
            if article_id is None:
                continue  # article was a duplicate and not inserted

            self.repo.link_tickers(article_id, tickers)


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

    def __init__(self, engine: Engine, transformers: list[ArticleTransformer]):
        self.repo = ArticleRepository(engine)
        self.transformers = transformers

    def run(self, transform_name: str | None = None) -> None:
        """
        Apply all (or one) transformer(s) to unprocessed articles.

        Args:
            transform_name: If provided, only run the transformer with this
                            transform_id. Useful for re-running a single step.
        """
        targets = self.transformers
        if transform_name:
            targets = [t for t in self.transformers if t.transform_id == transform_name]
            if not targets:
                _logger.error("No transformer found with id '%s'", transform_name)
                return

        for transformer in targets:
            _logger.info("Running transformer: %s", transformer.transform_id)
            try:
                articles = self.repo.get_untransformed(transformer.transform_id)
                if not articles:
                    _logger.info("No articles to transform for '%s'", transformer.transform_id)
                    continue

                enriched = transformer.transform(articles)
                self._persist(transformer, enriched)

            except Exception as exc:
                _logger.error(
                    "Transformer '%s' failed: %s", transformer.transform_id, exc
                )

    def _persist(self, transformer: ArticleTransformer, articles: list[dict]) -> None:
        """
        Write transformer results back to the database.

        Each transformer produces different output fields, so persistence
        logic is handled per transform_id.

        TODO: As transformers are implemented, add a branch here for each
              transform_id to persist its specific output fields.
              Example for sentiment:
                  UPDATE articles SET sentiment_score = :score WHERE id = :id

              Example for entity extraction:
                  repo.link_tickers(article["id"], article["mentioned_tickers"])
        """
        if transformer.transform_id == "entity_extraction":
            for article in articles:
                tickers = article.get("mentioned_tickers", [])
                if tickers:
                    self.repo.link_tickers(article["id"], tickers)

        # TODO: add persistence for sentiment_score and future transforms
        _logger.debug(
            "Persisted results for transformer '%s' (%d articles)",
            transformer.transform_id,
            len(articles),
        )
