"""
db/schema.py

SQLAlchemy table definitions for the news_articles module.

The articles table is the central store for all ingested news content.
Each row represents one unique article, identified by its URL.

Table: articles
    id           - Auto-incrementing surrogate key
    url          - Canonical article URL (unique — used for deduplication)
    title        - Headline text
    author       - Byline (may be NULL if not provided by the source)
    publisher    - Outlet name, e.g. "Reuters", "Bloomberg"
    source       - Extractor that produced this row, e.g. "rss", "newsapi"
    content      - Full article body text (plain text, no HTML)
    published_at - Publication timestamp from the source
    fetched_at   - Timestamp when this row was inserted (set by the DB)

Indexes:
    - (ticker, published_at) to support time-series lookups per company
    - published_at for date-range queries across all articles

Note on ticker linkage:
    Articles are linked to tickers via the article_tickers association table.
    This is a many-to-many relationship: one article may mention several
    companies, and one company may appear in many articles.
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
)

metadata = MetaData()

articles = Table(
    "articles",
    metadata,
    Column("id",           Integer,  primary_key=True, autoincrement=True),
    Column("url",          Text,     nullable=False, unique=True),
    Column("title",        Text,     nullable=True),
    Column("author",       Text,     nullable=True),
    Column("publisher",    String(255), nullable=True),
    Column("source",       String(64),  nullable=True),   # extractor identifier
    Column("content",      Text,     nullable=True),
    Column("published_at", DateTime, nullable=False),
    Column(
        "fetched_at",
        DateTime,
        nullable=False,
        server_default=func.now(),   # set by the DB on insert
    ),
)

# Association table: links articles to the tickers they mention.
# Populated by the entity extraction transformer once it identifies
# company mentions in the article content.
article_tickers = Table(
    "article_tickers",
    metadata,
    Column("article_id", Integer, ForeignKey("articles.id"), nullable=False),
    Column("ticker",     String(10),                         nullable=False),
)

# Indexes for common query patterns
Index("ix_articles_published_at",          articles.c.published_at)
Index("ix_article_tickers_ticker_pub",     article_tickers.c.ticker,
      article_tickers.c.article_id)
