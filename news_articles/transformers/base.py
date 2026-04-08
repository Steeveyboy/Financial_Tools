"""
transformers/base.py

Abstract base class for all article transformers.

Transformers run after articles are loaded into the database. This separation
means transforms can be re-run, applied retroactively to historical data, or
swapped out independently of the extraction process.

To add a new transform, subclass ArticleTransformer and implement `transform()`.

Example:
    class MyTransformer(ArticleTransformer):
        transform_id = "my_transform"

        def transform(self, articles: list[dict]) -> list[dict]:
            for article in articles:
                article["my_field"] = compute(article["content"])
            return articles
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ArticleTransformer(ABC):
    """
    Base class for all article transformers.

    Each transformer receives a list of article dicts (as returned by the
    repository) and returns an enriched list. Transformers must not modify
    the database directly — they return their results to the pipeline,
    which handles persistence.

    Subclasses must set `transform_id` (used for logging and the future
    transform_log table) and implement `transform()`.
    """

    #: Short identifier for this transform, e.g. "sentiment", "entity_extraction".
    transform_id: str = ""

    @abstractmethod
    def transform(self, articles: list[dict]) -> list[dict]:
        """
        Enrich a list of article dicts and return the updated list.

        Each article dict contains the columns from the articles table.
        Add new keys for any derived fields your transform produces.

        The pipeline will decide how to persist those new fields — this
        method should be a pure function with no side effects.

        Args:
            articles: List of article dicts to transform.

        Returns:
            The same list with new fields added per article.
        """
        ...
