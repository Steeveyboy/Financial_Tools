"""
extractors/rss.py

RSS feed extractor for financial news.

Parses one or more RSS/Atom feeds using feedparser and returns normalised
article dicts ready for the database. HTML is stripped from descriptions
using BeautifulSoup so the content field contains plain text only.

Configured for Reuters Business News by default, but accepts any list of
feed URLs so additional outlets can be added without changing this file.

Usage:
    from news_articles.extractors.rss import RSSExtractor

    extractor = RSSExtractor(feed_urls=[
        "https://feeds.reuters.com/reuters/businessNews",
    ])
    articles = extractor.extract()
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
from bs4 import BeautifulSoup

from .base import ArticleExtractor

_logger = logging.getLogger(__name__)

# Reuters Business News RSS feed. Additional feeds can be appended to this
# list or passed directly to RSSExtractor when constructing it.
REUTERS_BUSINESS_FEED = "https://feeds.reuters.com/reuters/businessNews"


def _strip_html(raw: str | None) -> str | None:
    """Remove HTML tags from a string, returning plain text."""
    if not raw:
        return None
    return BeautifulSoup(raw, "lxml").get_text(separator=" ", strip=True)


def _parse_date(date_str: str | None) -> datetime | None:
    """
    Parse an RFC 2822 date string (standard in RSS) to a UTC datetime.

    Returns None if the string is missing or unparseable.
    """
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        _logger.debug("Could not parse date string: %r", date_str)
        return None


class RSSExtractor(ArticleExtractor):
    """
    Fetches articles from one or more RSS/Atom feeds.

    Each feed is parsed independently so a failure in one does not prevent
    the others from being processed.

    Args:
        feed_urls: List of RSS feed URLs to poll. Defaults to Reuters Business.
    """

    source_id = "rss"

    def __init__(self, feed_urls: list[str] | None = None):
        self.feed_urls = feed_urls or [REUTERS_BUSINESS_FEED]

    def extract(self) -> list[dict]:
        """
        Parse all configured feeds and return normalised article dicts.

        Each dict contains: url, title, author, publisher, content,
        published_at. The `source` field is stamped by the pipeline.

        Returns:
            List of article dicts across all feeds, deduplicated by URL.
        """
        all_articles: list[dict] = []
        seen_urls: set[str] = set()

        for feed_url in self.feed_urls:
            try:
                articles = self._parse_feed(feed_url)
                for article in articles:
                    if article["url"] not in seen_urls:
                        seen_urls.add(article["url"])
                        all_articles.append(article)
            except Exception as exc:
                _logger.error("Failed to parse feed %s: %s", feed_url, exc)

        _logger.info("RSS extracted %d articles from %d feed(s)", len(all_articles), len(self.feed_urls))
        return all_articles

    def _parse_feed(self, feed_url: str) -> list[dict]:
        """Parse a single RSS feed and return its articles as dicts."""
        _logger.debug("Fetching feed: %s", feed_url)
        feed = feedparser.parse(feed_url)

        if feed.bozo:
            # feedparser sets bozo=True when the feed is malformed.
            # It still attempts to parse what it can, so we log and continue.
            _logger.warning("Feed %s is malformed: %s", feed_url, feed.bozo_exception)

        publisher = feed.feed.get("title", feed_url)
        articles = []

        for entry in feed.entries:
            url = entry.get("link")
            if not url:
                _logger.debug("Skipping entry with no URL in feed %s", feed_url)
                continue

            # Prefer full content over summary; strip HTML from either.
            raw_content = None
            if entry.get("content"):
                raw_content = entry.content[0].get("value")
            elif entry.get("summary"):
                raw_content = entry.get("summary")

            articles.append({
                "url":          url,
                "title":        entry.get("title"),
                "author":       entry.get("author"),
                "publisher":    publisher,
                "content":      _strip_html(raw_content),
                "published_at": _parse_date(entry.get("published")),
            })

        _logger.debug("Parsed %d entries from %s", len(articles), feed_url)
        return articles
