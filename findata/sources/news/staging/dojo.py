"""
staging/dojo.py

Loads the AlphaDojo/dojo_stock_news HuggingFace dataset (~4M rows) into the
``news.dojo_stock_news`` staging table, one row per source row.

Every run **appends**: the whole dataset is streamed, and only rows whose
``(url, page_symbol)`` pair is not staged yet are inserted (``INSERT … ON
CONFLICT DO NOTHING`` against the table's unique index). Re-running never
duplicates rows, and a run that fails partway is finished by running it again.
The table is created if it doesn't exist. ``replace=True`` clears it first.

Reading it back out, one row per article, is :func:`iter_staged_articles` —
used by ``extractors/dojo.py`` to normalize staging rows into ``news.articles``.

Usage:
    from findata.sources.news.staging.dojo import load_dojo_stock_news
    load_dojo_stock_news(limit=1000)
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import delete, func, inspect, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tqdm import tqdm

from findata.db.base import schema_translate_map_for
from findata.db.session import create_schemas, get_engine
from findata.models import DojoStockNews

_logger = logging.getLogger(__name__)

DATASET_NAME = "AlphaDojo/dojo_stock_news"

# Source columns copied straight across. The source ``id`` is dropped (see the
# model) and ``symbol`` is renamed to ``page_symbol``.
_TEXT_COLUMNS = [
    "title", "description", "url", "publisher", "publish_date", "ago",
    "primarysymbol", "on_symbol_json",
    "primarytopic", "primarytopic_url",
    "image", "imagedomain", "publisher_logo", "source",
]


#: The row identity the loader appends by; backed by this unique index.
_KEY_COLUMNS = ["url", "page_symbol"]
_KEY_INDEX = "ix_dojo_stock_news_url_page_symbol"


def _to_rows(batch: dict[str, list]) -> list[dict]:
    """Turn a columnar HuggingFace batch into a list of row dicts.

    Rows with no ``url`` are left out. NULLs never conflict in a unique index,
    so they would be staged again on every run, and ``DojoExtractor`` drops
    them anyway.
    """
    n = len(batch["url"])
    return [
        {
            # Renamed: the scraped-from page, not an article symbol. See the model.
            "page_symbol": batch["symbol"][i],
            **{col: batch[col][i] for col in _TEXT_COLUMNS},
        }
        for i in range(n)
        if batch["url"][i]
    ]


def _with_schema_map(engine: Engine | None) -> Engine:
    """Default to findata's engine and collapse schemas on SQLite."""
    engine = engine if engine is not None else get_engine()
    translate_map = schema_translate_map_for(engine.dialect.name)
    if translate_map:
        engine = engine.execution_options(schema_translate_map=translate_map)
    return engine


def _require_key_index(engine: Engine) -> None:
    """Fail loudly if the table predates its unique index.

    A table created before migration ``0003`` has no index to conflict on. The
    database would reject the first insert anyway, but with an obscure error and
    only after the dataset download has started.
    """
    table = DojoStockNews.__table__
    schema = engine.get_execution_options().get("schema_translate_map", {}).get(
        table.schema, table.schema
    )
    indexes = inspect(engine).get_indexes(table.name, schema=schema)
    if not any(ix["name"] == _KEY_INDEX for ix in indexes):
        raise RuntimeError(
            f"{table.name} has no {_KEY_INDEX} index, so new rows cannot be "
            "told from staged ones. Run `alembic upgrade head` first."
        )


def _count_rows(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(DojoStockNews)).scalar_one()


def _append_rows(engine: Engine, rows: list[dict]) -> None:
    """Insert *rows*, skipping any ``(url, page_symbol)`` already staged."""
    if not rows:
        return
    dialect_insert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    stmt = dialect_insert(DojoStockNews).on_conflict_do_nothing(index_elements=_KEY_COLUMNS)
    with Session(engine) as session:
        session.execute(stmt, rows)
        session.commit()


def load_dojo_stock_news(
    engine: Engine | None = None,
    batch_size: int = 5000,
    limit: int | None = None,
    replace: bool = False,
) -> int:
    """Append the dataset's not-yet-staged rows to ``news.dojo_stock_news``.

    Args:
        engine:     Target database. Defaults to findata's ``DATABASE_URL`` engine.
        batch_size: Rows per INSERT.
        limit:      Read only the first *limit* rows (for trying it out).
        replace:    Clear the table first, for a full refresh.

    Returns:
        Number of rows appended.
    """
    from datasets import load_dataset

    engine = _with_schema_map(engine)

    # Created here, not by Alembic, so a fresh database needs no migration step.
    create_schemas(engine)
    DojoStockNews.__table__.create(engine, checkfirst=True)
    _require_key_index(engine)

    if replace:
        with Session(engine) as session:
            cleared = session.execute(delete(DojoStockNews)).rowcount
            session.commit()
        _logger.info("Cleared %d existing rows from dojo_stock_news", cleared)

    staged_before = _count_rows(engine)

    dataset = load_dataset(DATASET_NAME, split="train", streaming=True)
    if limit is not None:
        dataset = dataset.take(limit)

    _logger.info("Streaming %s (batch_size=%d, limit=%s)", DATASET_NAME, batch_size, limit)

    streamed = 0
    no_url = 0
    progress = tqdm(desc="dojo_stock_news", unit=" rows", total=limit)
    for batch in dataset.iter(batch_size=batch_size):
        batch_rows = len(batch["url"])
        rows = _to_rows(batch)
        _append_rows(engine, rows)
        streamed += batch_rows
        no_url += batch_rows - len(rows)
        progress.update(batch_rows)
    progress.close()

    # Counted, not summed from rowcount: drivers disagree on what a batched
    # ON CONFLICT insert reports.
    appended = _count_rows(engine) - staged_before
    _logger.info(
        "dojo_stock_news: streamed %d rows, appended %d new, skipped %d already staged%s",
        streamed,
        appended,
        streamed - no_url - appended,
        f", dropped {no_url} with no url" if no_url else "",
    )
    return appended


def iter_staged_articles(
    engine: Engine | None = None,
    batch_size: int = 500,
) -> Iterator[list[dict]]:
    """Yield the staging table back as one dict per article (distinct ``url``).

    Each dict is the article's first staging row (lowest ``id``) plus
    ``page_symbols``: every ``page_symbol`` the URL was listed under, across
    all its rows. For eastmoney rows that is the only symbol data there is —
    see ``docs/discoveries/007-dojo-symbol-column.md``.

    Two steps rather than one streamed query: an open read cursor on SQLite
    would block the pipeline's writes between batches. Step 1 holds one small
    tuple per article in memory (~1.6M for the full dataset).
    """
    engine = _with_schema_map(engine)
    t = DojoStockNews.__table__

    firsts = (
        select(
            func.min(t.c.id).label("first_id"),
            func.aggregate_strings(t.c.page_symbol, ",").label("page_symbols"),
        )
        .group_by(t.c.url)
        .order_by(func.min(t.c.id))
    )
    with engine.connect() as conn:
        articles = conn.execute(firsts).all()
    _logger.info("dojo_stock_news: %d distinct articles to read", len(articles))

    columns = [c for c in t.c if c.name not in ("created_at", "updated_at")]
    for start in range(0, len(articles), batch_size):
        chunk = articles[start : start + batch_size]
        symbols_by_id = {
            first_id: page_symbols.split(",") if page_symbols else []
            for first_id, page_symbols in chunk
        }
        stmt = select(*columns).where(t.c.id.in_(symbols_by_id)).order_by(t.c.id)
        with engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        yield [{**row, "page_symbols": symbols_by_id[row["id"]]} for row in rows]
