"""
extractors/rss.py

RSS feed extractor stub.

RSS feeds are the first planned source for Resonance Desk. Most financial
news outlets publish RSS feeds (Reuters, MarketWatch, Seeking Alpha, etc.).

To implement:
    1. Add `feedparser` to requirements.txt
    2. Fill in the `extract()` method below
    3. Pass a list of feed URLs when constructing RSSExtractor

Usage (once implemented):
    extractor = RSSExtractor(feed_urls=[
        "https://feeds.reuters.com/reuters/businessNews",
        "https://feeds.marketwatch.com/marketwatch/topstories",
    ])
    articles = extractor.extract()
"""

from __future__ import annotations

import logging

from .base import ArticleExtractor

_logger = logging.getLogger(__name__)


class RSSExtractor(ArticleExtractor):
    """
    Fetches articles from one or more RSS/Atom feeds.

    Args:
        feed_urls: List of RSS feed URLs to poll.
    """

    source_id = "rss"

    def __init__(self, feed_urls: list[str]):
        self.feed_urls = feed_urls

    def extract(self) -> list[dict]:
        """
        Parse each feed and return normalised article dicts.

        TODO:
            - Install feedparser: pip install feedparser
            - For each URL in self.feed_urls:
                  feed = feedparser.parse(url)
                  for entry in feed.entries:
                      yield {
                          "url":          entry.link,
                          "title":        entry.get("title"),
                          "author":       entry.get("author"),
                          "publisher":    feed.feed.get("title"),
                          "content":      _extract_content(entry),
                          "published_at": _parse_date(entry.get("published")),
                      }
            - Strip HTML from content before returning (use BeautifulSoup)
            - Handle entries with missing `link` (skip them)
            - Handle network errors per-feed so one bad feed doesn't abort others
        """
        _logger.warning(
            "RSSExtractor.extract() is not yet implemented — returning empty list"
        )
        return []
