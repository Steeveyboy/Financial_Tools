"""
Article model — one ingested news article, identified by its URL.

The URL is the deduplication key (unique). Articles are linked to the tickers
they mention via :class:`~findata.models.article_ticker.ArticleTicker`
(many-to-many).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from findata.db.base import Base

if TYPE_CHECKING:
    from .article_ticker import ArticleTicker


class Article(Base):
    """A news article ingested by one of the news extractors.

    Attributes:
        id:           Auto-incrementing primary key.
        url:          Canonical article URL — unique, used for deduplication.
        title:        Headline text.
        author:       Byline (nullable).
        publisher:    Outlet name, e.g. ``Reuters``, ``Bloomberg``.
        source:       Extractor identifier that produced this row, e.g. ``rss``.
        content:      Full article body text (plain text, no HTML).
        published_at: Publication timestamp reported by the source.
        fetched_at:   Timestamp this row was inserted (set by the DB).
        tickers:      Linked ticker associations.
    """

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_articles_published_at", "published_at"),
    )

    tickers: Mapped[List["ArticleTicker"]] = relationship(
        "ArticleTicker",
        back_populates="article",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Article(url={self.url!r})>"
