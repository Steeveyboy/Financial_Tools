"""
models/article.py

News articles. Phase 1 (extraction) writes these; Phase 2 (transform) updates
``sentiment_score`` in place. See ``findata/sources/news/README.md``.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from findata.db.base import SCHEMA_NEWS, Base
from findata.models.mixins import UTCDateTime, TimestampMixin


class Article(TimestampMixin, Base):
    """A single news article."""

    __tablename__ = "articles"
    __table_args__ = {"schema": SCHEMA_NEWS}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    #: The deduplication key for the whole news pipeline.
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    #: Who published the article — ``Reuters``, ``Bloomberg``.
    publisher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    #: Which *extractor* produced this row — ``rss``, ``fnspid``. Was ``source``,
    #: which gave no clue how it differed from ``publisher``.
    ingest_source: Mapped[str] = mapped_column(String(32), nullable=False)

    #: Event time, always tz-aware. NOT NULL on purpose: an article with no
    #: timestamp cannot enter a time series, so it is not worth a row.
    #: ``ArticleRepository.insert_articles()`` filters and counts the ones
    #: extractors emit without a date rather than letting the INSERT raise.
    published_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, index=True
    )

    #: Signed FinBERT score in ``[-1.0, 1.0]``; ``NULL`` means "not scored" or
    #: "no usable text" — ``news.article_transforms`` disambiguates.
    #: See ``docs/SENTIMENT_TRANSFORM.md``.
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    securities: Mapped[List["ArticleSecurity"]] = relationship(  # noqa: F821
        "ArticleSecurity",
        back_populates="article",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Article(url={self.url!r})>"
