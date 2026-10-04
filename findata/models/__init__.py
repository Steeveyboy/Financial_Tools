"""
findata.models package.

Importing this package registers every ORM model on ``Base.metadata``, which is
what makes ``Base.metadata`` the authoritative table list for Alembic
autogenerate and :func:`findata.db.session.init_db`.

A new model is not part of the warehouse until it is imported here.
"""

from findata.db.base import (
    ALL_SCHEMAS,
    SCHEMA_MARKET,
    SCHEMA_NEWS,
    SCHEMA_REFERENCE,
    Base,
)

# news — articles and their derived data
from .article import Article
from .article_security import ArticleSecurity
from .article_transform import ArticleTransform
from .company import Company

# market — price time series
from .daily_bar import DailyBar

# news — staging copies of upstream datasets
from .dojo_stock_news import DojoStockNews

# reference — slowly-changing dimensions
from .exchange import Exchange
from .insider import Insider
from .mixins import TimestampMixin, UTCDateTime

__all__ = [
    "ALL_SCHEMAS",
    "SCHEMA_MARKET",
    "SCHEMA_NEWS",
    "SCHEMA_REFERENCE",
    "Base",
    "TimestampMixin",
    "UTCDateTime",
    "Exchange",
    "Company",
    "Insider",
    "DailyBar",
    "Article",
    "ArticleSecurity",
    "ArticleTransform",
    "DojoStockNews",
]
