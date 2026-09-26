"""Shared pytest fixtures.

Every database test runs against a fresh in-memory SQLite database. Nothing here
touches a real Postgres instance: ``DATABASE_URL`` is forced to ``sqlite://``
*before* ``findata`` is imported, so even a stray ``get_engine()`` call inside
the code under test cannot reach the developer's warehouse.

SQLite has no schemas, so the engine fixtures apply the project's
``schema_translate_map`` — the models all declare ``schema=``, and without the
map SQLite would be asked for ``news.articles``. ``ArticleRepository`` applies it
to an injected engine too; the fixture does it as well so engines handed to other
code behave the same.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

# Must happen before any findata import — findata.config reads the environment
# (and the repo-root .env) at import time.
os.environ["DATABASE_URL"] = "sqlite://"

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from findata.db.base import schema_translate_map_for  # noqa: E402
from findata.models import Base  # noqa: E402
from findata.sources.news.db.repository import ArticleRepository  # noqa: E402


@pytest.fixture
def engine():
    """A fresh in-memory SQLite engine with the schema map applied."""
    eng = create_engine("sqlite://").execution_options(
        schema_translate_map=schema_translate_map_for("sqlite")
    )
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def all_tables(engine):
    """An engine with every warehouse table created, not just the news ones."""
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def repo(engine):
    """An :class:`ArticleRepository` with the news tables created."""
    repository = ArticleRepository(engine)
    repository.create_tables()
    return repository


@pytest.fixture
def sample_articles() -> list[dict]:
    """Two well-formed article rows, as an extractor would emit them.

    ``published_at`` is aware: extractors normalise through
    :func:`findata.db.types.ensure_utc`, and ``articles.published_at`` is
    ``timestamptz``.
    """
    return [
        {
            "url": "https://example.com/a",
            "title": "Widgets Inc beats expectations",
            "author": "A. Reporter",
            "publisher": "Example Wire",
            "ingest_source": "test",
            "content": "Widgets Inc reported record quarterly revenue.",
            "published_at": datetime(2026, 1, 2, 9, 30, tzinfo=timezone.utc),
        },
        {
            "url": "https://example.com/b",
            "title": "Cogs Corp warns on guidance",
            "author": None,
            "publisher": "Example Wire",
            "ingest_source": "test",
            "content": "Cogs Corp cut its full-year outlook.",
            "published_at": datetime(2026, 1, 3, 14, 0, tzinfo=timezone.utc),
        },
    ]
