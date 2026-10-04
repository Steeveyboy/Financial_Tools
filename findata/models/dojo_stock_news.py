"""
models/dojo_stock_news.py

Staging table for the AlphaDojo/dojo_stock_news HuggingFace dataset.

A raw copy of the dataset: every source column is kept, as text, exactly as it
arrives. No deduplication, no parsing — the same article URL appears once per
stock page it was scraped from. A later transform normalizes these rows into
``news.articles`` / ``news.article_securities``.

This table deliberately breaks the "named for what a row is, not its source"
rule in ``docs/DATA_MODEL.md``: a staging table *is* its source.

One column is renamed: the source's ``symbol`` is stored as ``page_symbol``.
It is the stock page the row was scraped from, and almost never a symbol the
article mentions — those are in ``on_symbol_json``. ``symbol`` is reserved for
joinable tickers (``String(32)``, enforced by the naming tests).
See ``docs/discoveries/007-dojo-symbol-column.md``.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from findata.db.base import SCHEMA_NEWS, Base
from findata.models.mixins import TimestampMixin


class DojoStockNews(TimestampMixin, Base):
    """One row per row of the source dataset."""

    __tablename__ = "dojo_stock_news"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The dataset's own ``id`` is not kept: it is float64, so large values are
    # rounded, and some exceed bigint. ``url`` identifies duplicate articles.

    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    #: e.g. ``"Sep 26, 2026"`` — date only, unparsed.
    publish_date: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    #: Relative age at scrape time, e.g. ``"13 hours ago"``.
    ago: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    #: The source's ``symbol``: the stock page this row was scraped from — see
    #: module docstring.
    page_symbol: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    #: Lowercase primary symbol of the article, e.g. ``"nvda"``.
    primarysymbol: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    #: JSON list of ``{"symbol": ..., "type": ...}`` — the article's symbols.
    on_symbol_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    primarytopic: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primarytopic_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    imagedomain: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publisher_logo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = ({"schema": SCHEMA_NEWS},)

    def __repr__(self) -> str:
        return f"<DojoStockNews(id={self.id}, url={self.url!r})>"
