"""
extractors/base.py

Abstract base class for all article extractors.

To add a new source, subclass ArticleExtractor and implement `extract()`.
The pipeline will call it without knowing what source it is.

Example:
    class MyExtractor(ArticleExtractor):
        ingest_source = "my_source"

        def extract(self) -> list[dict]:
            ...  # fetch and return article dicts
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator


class ArticleExtractor(ABC):
    """
    Base class for all news article sources.

    Each extractor is responsible for fetching raw articles from one source
    and returning them in a normalised dict format that matches the articles
    table schema.

    Subclasses must set `ingest_source` (a short string identifying which
    extractor produced the row, stored in news.articles.ingest_source) and
    implement `extract()`.

    Extractors may implement `extract_batches()` instead of (or in addition
    to) `extract()` to yield articles in chunks. This avoids holding the
    entire dataset in memory. The pipeline will prefer `extract_batches()`
    when available.
    """

    #: Short identifier stored in news.articles.ingest_source, e.g. "rss",
    #: "fnspid". Must be unique across all extractors. Named for the column it
    #: fills: it is a name, not an integer surrogate key, so it is not a *_id.
    ingest_source: str = ""

    #: Default batch size for extractors that support batched extraction.
    batch_size: int = 500

    @abstractmethod
    def extract(self) -> list[dict]:
        """
        Fetch articles from the source and return them as normalised dicts.

        Each dict must contain at minimum:
            url          (str)      - Canonical article URL (used for dedup)
            title        (str)      - Headline
            published_at (datetime) - Publication timestamp

        These fields are optional but strongly recommended:
            author    (str)
            publisher (str)
            content   (str)  - Plain text body (strip HTML before returning)

        `published_at` must be timezone-aware, or None if the feed gave no
        usable date — undated articles are dropped at insert time, not here.
        Use findata.db.types.ensure_utc() to normalise whatever the feed
        provides.

        The `ingest_source` field is set automatically to
        `self.ingest_source` by the pipeline — you need not include it.

        Returns:
            List of article dicts ready to pass to ArticleRepository.insert_articles().
        """
        ...

    def extract_batches(self) -> Iterator[list[dict]]:
        """
        Yield articles in batches rather than accumulating all at once.

        Default implementation calls extract() and yields a single batch.
        Override this for sources that stream large datasets.
        """
        yield self.extract()

    def _tag_source(self, articles: list[dict]) -> list[dict]:
        """Stamp each article dict with this extractor's ingest_source."""
        for article in articles:
            article.setdefault("ingest_source", self.ingest_source)
        return articles
