"""
models/article_transform.py

Which transforms have been applied to which articles.

Renamed from ``transform_log``: plural per the naming standard, and "log" named
the mechanism rather than the contents. ``transform_id`` became
``transform_name`` because it holds a string like ``"sentiment"`` — a ``*_id``
column is an integer surrogate key or a foreign key to one, never free text. The
repository's Python parameter was already called ``transform_name``, so this also
closes a long-standing mismatch between argument and column.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import ForeignKey

from findata.db.base import SCHEMA_NEWS, Base
from findata.models.mixins import UTCDateTime


class ArticleTransform(Base):
    """One row per ``(article, transform)`` application.

    A row records the **attempt**, not the result. That is what lets a ``NULL``
    ``articles.sentiment_score`` carry two distinct meanings safely:

    - no row here → never scored, will be picked up
    - a row here + ``NULL`` score → scored, but the article had no usable text;
      **not** retried

    Without it, every empty-content article gets rescored on every run forever.
    See ``docs/SENTIMENT_TRANSFORM.md``.

    This table does not use :class:`TimestampMixin`: ``transformed_at`` already
    *is* its write timestamp, and a second identical column would be noise.
    """

    __tablename__ = "article_transforms"

    article_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{SCHEMA_NEWS}.articles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    #: Transform identifier — ``sentiment``, ``entity``.
    transform_name: Mapped[str] = mapped_column(String(64), primary_key=True)

    transformed_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # The anti-join path in ArticleRepository.get_untransformed(): find
        # articles with no row for a given transform_name. Leading with
        # transform_name is what makes that seek rather than scan.
        Index("ix_article_transforms_transform_name_article_id",
              "transform_name", "article_id"),
        {"schema": SCHEMA_NEWS},
    )

    def __repr__(self) -> str:
        return (
            f"<ArticleTransform(article_id={self.article_id}, "
            f"transform_name={self.transform_name!r})>"
        )
