"""
extractors/dojo.py

Normalizes the ``news.dojo_stock_news`` staging table into ``news.articles`` /
``news.article_securities``. Unlike the other extractors this reads from the
database, not the network: run ``load_dojo_stock_news.py`` first.

The staging table holds two populations with different shapes — see
``docs/discoveries/007-dojo-symbol-column.md``:

    English (``source`` NULL)   symbols from ``on_symbol_json``; ``page_symbol``
                                is the page it was scraped from and is ignored.
                                ``publish_date`` is date-only ("Oct 3, 2026").
    eastmoney                   no ``on_symbol_json``; the article's
                                ``page_symbol`` values (e.g. ``601398.SS``) are
                                its only symbols. ``publish_date`` is ISO 8601.

Lossy choices, made on purpose:
    - A date-only ``publish_date`` becomes 00:00 UTC; the source has no time.
    - Only ``stocks`` and ``etf`` entries of ``on_symbol_json`` are linked;
      ``crypto``, ``index`` and ``mutualfunds`` are not securities we track.

Usage:
    from findata.sources.news.extractors.dojo import DojoExtractor

    for batch in DojoExtractor().extract_batches():
        repo.insert_articles(batch)
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import datetime

from findata.db.types import ensure_utc
from findata.sources.news.staging.dojo import iter_staged_articles

from .base import ArticleExtractor

_logger = logging.getLogger(__name__)

#: ``on_symbol_json`` entry types that are linked to the article.
_LINKED_SYMBOL_TYPES = frozenset({"stocks", "etf"})

_DATE_ONLY_FORMATS = ["%b %d, %Y", "%Y-%m-%d"]


def _parse_publish_date(value: str | None) -> datetime | None:
    """Parse either population's ``publish_date`` to an aware UTC datetime.

    Returns ``None`` for anything unparseable; ``insert_articles`` drops and
    counts undated articles.
    """
    if not value:
        return None
    value = value.strip()
    try:
        # eastmoney: "2026-10-04T08:49:28+00:00"
        return ensure_utc(datetime.fromisoformat(value))
    except ValueError:
        pass
    for fmt in _DATE_ONLY_FORMATS:
        try:
            return ensure_utc(datetime.strptime(value, fmt))
        except ValueError:
            continue
    _logger.debug("Could not parse dojo publish_date: %r", value)
    return None


def _symbols_from_json(raw: str | None) -> list[str]:
    """The ``stocks``/``etf`` symbols in an ``on_symbol_json`` list."""
    if not raw:
        return []
    try:
        entries = json.loads(raw)
    except ValueError:
        _logger.debug("Bad on_symbol_json: %r", raw[:200])
        return []
    return [
        e["symbol"]
        for e in entries
        if isinstance(e, dict) and e.get("symbol") and e.get("type") in _LINKED_SYMBOL_TYPES
    ]


class DojoExtractor(ArticleExtractor):
    """
    Reads staged AlphaDojo/dojo_stock_news rows, one article per URL.

    Args:
        batch_size: Articles per batch yielded by extract_batches().
    """

    ingest_source = "dojo"

    def __init__(self, batch_size: int = 500):
        self.batch_size = batch_size

    def extract(self) -> list[dict]:
        """Return all staged articles as one list. Prefer extract_batches()."""
        all_articles = []
        for batch in self.extract_batches():
            all_articles.extend(batch)
        return all_articles

    def extract_batches(self) -> Iterator[list[dict]]:
        for rows in iter_staged_articles(batch_size=self.batch_size):
            batch = [a for a in (self._normalise(r) for r in rows) if a is not None]
            if batch:
                yield batch

    def _normalise(self, row: dict) -> dict | None:
        """Map one staging row (plus its ``page_symbols``) to an article dict."""
        if not row["url"]:
            return None

        if row["source"] == "eastmoney":
            symbols = row["page_symbols"]
        else:
            symbols = _symbols_from_json(row["on_symbol_json"])

        return {
            "url":               row["url"],
            "title":             row["title"],
            # eastmoney rows have no publisher; the site is the publisher.
            "publisher":         row["publisher"] or row["source"],
            "content":           row["description"] or None,
            "published_at":      _parse_publish_date(row["publish_date"]),
            "mentioned_symbols": symbols,
        }
