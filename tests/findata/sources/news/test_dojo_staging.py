"""Tests for the dojo_stock_news staging loader's append contract.

``load_dojo_stock_news`` re-streams the whole dataset on every run and relies on
the database to discard what is already staged. These tests are about that
contract — a row is identified by ``(url, page_symbol)`` — and never touch
HuggingFace.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from findata.models import DojoStockNews
from findata.sources.news.staging import dojo
from findata.sources.news.staging.dojo import (
    _append_rows,
    _count_rows,
    _require_key_index,
    _to_rows,
    load_dojo_stock_news,
)


@pytest.fixture
def staged(engine):
    """An engine with the staging table (and its unique index) created."""
    DojoStockNews.__table__.create(engine)
    return engine


def _row(url: str | None, page_symbol: str | None, title: str = "t") -> dict:
    return {"url": url, "page_symbol": page_symbol, "title": title}


def _batch(*pairs: tuple[str | None, str | None]) -> dict[str, list]:
    """A columnar HuggingFace batch holding one row per ``(url, symbol)``."""
    batch: dict[str, list] = {col: [None] * len(pairs) for col in dojo._TEXT_COLUMNS}
    batch["url"] = [url for url, _ in pairs]
    batch["symbol"] = [symbol for _, symbol in pairs]
    return batch


def test_appending_the_same_rows_twice_stores_them_once(staged):
    rows = [_row("https://example.com/a", "NVDA"), _row("https://example.com/b", "NVDA")]

    _append_rows(staged, rows)
    _append_rows(staged, rows)

    assert _count_rows(staged) == 2


def test_new_url_is_appended(staged):
    _append_rows(staged, [_row("https://example.com/a", "NVDA")])
    _append_rows(staged, [_row("https://example.com/b", "NVDA")])

    assert _count_rows(staged) == 2


def test_known_url_on_a_new_page_is_appended(staged):
    """eastmoney articles get their symbols from the pages they are listed on."""
    _append_rows(staged, [_row("https://example.com/a", "601398.SS")])
    _append_rows(staged, [_row("https://example.com/a", "1398.HK")])

    assert _count_rows(staged) == 2


def test_duplicate_pair_inside_one_batch_is_stored_once(staged):
    _append_rows(staged, [_row("https://example.com/a", "NVDA")] * 2)

    assert _count_rows(staged) == 1


def test_staged_row_is_not_overwritten(staged):
    _append_rows(staged, [_row("https://example.com/a", "NVDA", title="first")])
    _append_rows(staged, [_row("https://example.com/a", "NVDA", title="second")])

    with staged.connect() as conn:
        assert conn.execute(select(DojoStockNews.title)).scalars().all() == ["first"]


def test_to_rows_drops_rows_with_no_url():
    rows = _to_rows(_batch(("https://example.com/a", "NVDA"), (None, "NVDA"), ("", "TAN")))

    assert [(r["url"], r["page_symbol"]) for r in rows] == [("https://example.com/a", "NVDA")]


def test_table_without_the_unique_index_is_rejected(engine):
    """A table staged before migration 0003 must not be appended to blindly."""
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE dojo_stock_news (id INTEGER PRIMARY KEY, url TEXT)")

    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        _require_key_index(engine)


@pytest.fixture
def fake_dataset(monkeypatch):
    """Stand in for ``datasets.load_dataset``; set ``.pairs`` to what it streams."""

    class _Dataset:
        pairs: list[tuple[str | None, str | None]] = []

        def take(self, n):
            limited = _Dataset()
            limited.pairs = self.pairs[:n]
            return limited

        def iter(self, batch_size):
            for start in range(0, len(self.pairs), batch_size):
                yield _batch(*self.pairs[start : start + batch_size])

    dataset = _Dataset()
    import datasets

    monkeypatch.setattr(datasets, "load_dataset", lambda *args, **kwargs: dataset)
    return dataset


def test_second_run_appends_only_the_new_rows(engine, fake_dataset):
    fake_dataset.pairs = [("https://example.com/a", "NVDA"), ("https://example.com/a", "TAN")]
    assert load_dojo_stock_news(engine, batch_size=1) == 2

    fake_dataset.pairs.append(("https://example.com/b", "NVDA"))
    assert load_dojo_stock_news(engine, batch_size=1) == 1
    assert _count_rows(engine) == 3


def test_replace_clears_the_table_first(engine, fake_dataset):
    fake_dataset.pairs = [("https://example.com/a", "NVDA"), ("https://example.com/b", "NVDA")]
    load_dojo_stock_news(engine)

    fake_dataset.pairs = [("https://example.com/c", "NVDA")]
    assert load_dojo_stock_news(engine, replace=True) == 1
    assert _count_rows(engine) == 1
