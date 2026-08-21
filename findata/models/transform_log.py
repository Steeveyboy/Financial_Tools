"""
TransformLog model — records which transforms have been applied to which
articles.

Phase 2 of the news ETL is re-runnable by design: transforms can be applied
retroactively to the full historical article set without re-fetching. That
only works if the pipeline can answer "which articles has transform X *not*
seen yet?" — which is what this table is for.

A row here means "transform ``transform_id`` ran on article ``article_id``",
regardless of the outcome. That distinction matters: an article with no usable
text gets a ``NULL`` :attr:`~findata.models.article.Article.sentiment_score`,
which is indistinguishable from "never scored" if you only look at the column.
Logging the attempt is what stops the pipeline retrying those rows forever.

The composite primary key ``(article_id, transform_id)`` makes the log
idempotent under ``INSERT ... ON CONFLICT DO NOTHING``, so a transform batch
that partially fails can simply be re-run.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from findata.db.base import Base


class TransformLog(Base):
    """One (article, transform) pair that has been processed.

    Attributes:
        article_id:     FK to :class:`~findata.models.article.Article`.
        transform_id:   Transformer identifier, e.g. ``sentiment``.
        transformed_at: When the transform ran (set by the DB).
    """

    __tablename__ = "transform_log"

    article_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    transform_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    transformed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Supports the anti-join in ArticleRepository.get_untransformed(),
        # which filters by transform_id first, then probes by article_id.
        Index("ix_transform_log_transform_article", "transform_id", "article_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<TransformLog(article_id={self.article_id}, "
            f"transform_id={self.transform_id!r})>"
        )
