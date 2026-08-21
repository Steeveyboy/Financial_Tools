"""Smoke tests for :class:`ArticleRepository`.

These are deliberately about the repository's *contracts* — deduplication and
idempotence — because those are what the two-phase pipeline relies on when
extraction and transforms are re-run over the same data.
"""

from __future__ import annotations

from datetime import datetime


def test_insert_articles_inserts_rows(repo, sample_articles):
    assert repo.insert_articles(sample_articles) == 2
    assert len(repo.get_all()) == 2


def test_insert_articles_empty_batch_is_a_noop(repo):
    assert repo.insert_articles([]) == 0
    assert repo.get_all() == []


def test_insert_articles_skips_urls_already_stored(repo, sample_articles):
    repo.insert_articles(sample_articles)

    # Same batch again — every URL already exists.
    assert repo.insert_articles(sample_articles) == 0
    assert len(repo.get_all()) == 2


def test_insert_articles_dedupes_within_a_single_batch(repo, sample_articles):
    """FNSPID emits the same URL once per ticker — one batch, duplicate rows."""
    duplicated = sample_articles + [dict(sample_articles[0])]

    assert repo.insert_articles(duplicated) == 2
    assert len(repo.get_all()) == 2


def test_insert_articles_ignores_non_column_keys(repo):
    """Extractors may attach ``mentioned_tickers``; it isn't a column."""
    row = {
        "url": "https://example.com/c",
        "title": "Sprockets Ltd announces buyback",
        "source": "test",
        "published_at": datetime(2026, 1, 4, 8, 0),
        "mentioned_tickers": ["SPRK"],
    }

    assert repo.insert_articles([row]) == 1
    assert repo.get_all()[0]["url"] == "https://example.com/c"


def test_link_tickers_is_idempotent(repo, sample_articles):
    repo.insert_articles(sample_articles)
    article_id = repo.get_id_by_url("https://example.com/a")

    repo.link_tickers(article_id, ["AAPL", "MSFT"])
    repo.link_tickers(article_id, ["AAPL", "MSFT"])  # re-run of the transform

    assert len(repo.get_by_ticker("AAPL")) == 1
    assert len(repo.get_by_ticker("MSFT")) == 1


def test_link_tickers_with_no_tickers_is_a_noop(repo, sample_articles):
    repo.insert_articles(sample_articles)
    article_id = repo.get_id_by_url("https://example.com/a")

    repo.link_tickers(article_id, [])

    assert repo.get_by_ticker("AAPL") == []


def test_bulk_link_tickers_dedupes_within_the_batch(repo, sample_articles):
    repo.insert_articles(sample_articles)
    ids = repo.get_ids_by_urls([a["url"] for a in sample_articles])

    links = [
        {"article_id": ids["https://example.com/a"], "ticker": "AAPL"},
        {"article_id": ids["https://example.com/a"], "ticker": "AAPL"},
        {"article_id": ids["https://example.com/b"], "ticker": "AAPL"},
    ]
    repo.bulk_link_tickers(links)

    assert len(repo.get_by_ticker("AAPL")) == 2


def test_get_by_ticker_returns_newest_first(repo, sample_articles):
    repo.insert_articles(sample_articles)
    ids = repo.get_ids_by_urls([a["url"] for a in sample_articles])
    repo.bulk_link_tickers(
        [{"article_id": aid, "ticker": "AAPL"} for aid in ids.values()]
    )

    urls = [a["url"] for a in repo.get_by_ticker("AAPL")]

    # b is published a day after a.
    assert urls == ["https://example.com/b", "https://example.com/a"]


def test_get_ids_by_urls_only_returns_known_urls(repo, sample_articles):
    repo.insert_articles(sample_articles)

    ids = repo.get_ids_by_urls(
        ["https://example.com/a", "https://example.com/missing"]
    )

    assert list(ids) == ["https://example.com/a"]
    assert repo.get_id_by_url("https://example.com/missing") is None


def test_get_ids_by_urls_with_empty_input(repo):
    assert repo.get_ids_by_urls([]) == {}
