"""
ArticleTicker model — association between an article and a ticker it mentions.

Many-to-many: one article may mention several companies, and one company may
appear in many articles. The pair ``(article_id, ticker)`` is the primary key,
so an article links to a given ticker at most once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from findata.db.base import Base

if TYPE_CHECKING:
    from .article import Article


class ArticleTicker(Base):
    """Links :class:`~findata.models.article.Article` rows to ticker symbols."""

    __tablename__ = "article_tickers"

    article_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)

    __table_args__ = (
        Index("ix_article_tickers_ticker_article", "ticker", "article_id"),
    )

    article: Mapped["Article"] = relationship("Article", back_populates="tickers")

    def __repr__(self) -> str:
        return f"<ArticleTicker(article_id={self.article_id}, ticker={self.ticker!r})>"
