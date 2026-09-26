"""
models/article_security.py

Which securities an article mentions.

Renamed from ``article_tickers`` — the warehouse uses one term, ``symbol``, and
the table is named for the entities it links rather than for the column type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from findata.db.base import SCHEMA_NEWS, Base
from findata.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from .article import Article


class ArticleSecurity(TimestampMixin, Base):
    """A ``(article, symbol)`` mention link.

    The composite primary key is what makes re-running extraction idempotent:
    inserts use a dialect-aware ``INSERT … ON CONFLICT DO NOTHING``, so the same
    article/symbol pair can be offered any number of times.

    Phase 8 (``docs/CLEANUP_PLAN.md``) adds a nullable ``security_id`` FK beside
    ``symbol`` and keeps ``symbol`` in the key, so unresolvable mentions are
    still recorded and can be resolved in place later.
    """

    __tablename__ = "article_securities"

    article_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{SCHEMA_NEWS}.articles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    #: The symbol as the extractor emitted it, uppercased. ``String(32)``
    #: matches ``reference.companies.symbol`` and ``market.daily_bars.symbol`` —
    #: previously this was ``String(10)`` against a ``String(20)`` elsewhere, so
    #: a symbol that stored in one table was rejected by the next.
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)

    #: How the link was made — ``extractor`` (the feed supplied it) or
    #: ``entity_transform`` (inferred from the text). Provenance matters because
    #: the two have very different precision.
    link_source: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        # Covers "every article mentioning X", the query the demo runs most.
        Index("ix_article_securities_symbol_article_id", "symbol", "article_id"),
        CheckConstraint("symbol = upper(symbol)", name="symbol_uppercase"),
        {"schema": SCHEMA_NEWS},
    )

    article: Mapped["Article"] = relationship("Article", back_populates="securities")

    def __repr__(self) -> str:
        return (
            f"<ArticleSecurity(article_id={self.article_id}, symbol={self.symbol!r})>"
        )
