"""
extractors/base.py

Abstract base class for all article extractors.

To add a new source, subclass ArticleExtractor and implement `extract()`.
The pipeline will call it without knowing what source it is.

Example:
    class MyExtractor(ArticleExtractor):
        source_id = "my_source"

        def extract(self) -> list[dict]:
            ...  # fetch and return article dicts
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ArticleExtractor(ABC):
    """
    Base class for all news article sources.

    Each extractor is responsible for fetching raw articles from one source
    and returning them in a normalised dict format that matches the articles
    table schema.

    Subclasses must set `source_id` (a short string identifying the source,
    stored in the articles.source column) and implement `extract()`.
    """

    #: Short identifier stored in the articles.source column, e.g. "rss", "newsapi".
    #: Must be unique across all extractors.
    source_id: str = ""

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

        The `source` field will be set automatically to `self.source_id`
        by the pipeline before inserting — you do not need to include it.

        Returns:
            List of article dicts ready to pass to ArticleRepository.insert_articles().
        """
        ...

    def _tag_source(self, articles: list[dict]) -> list[dict]:
        """Stamp each article dict with this extractor's source_id."""
        for article in articles:
            article.setdefault("source", self.source_id)
        return articles
