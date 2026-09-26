"""Smoke tests for :class:`ArticleRepository`.

These are deliberately about the repository's *contracts* — deduplication and
idempotence — because those are what the two-phase pipeline relies on when
extraction and transforms are re-run over the same data.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


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
    """FNSPID emits the same URL once per symbol — one batch, duplicate rows."""
    duplicated = sample_articles + [dict(sample_articles[0])]

    assert repo.insert_articles(duplicated) == 2
    assert len(repo.get_all()) == 2


def test_insert_articles_ignores_non_column_keys(repo):
    """Extractors may attach ``mentioned_symbols``; it isn't a column."""
    row = {
        "url": "https://example.com/c",
        "title": "Sprockets Ltd announces buyback",
        "ingest_source": "test",
        "published_at": datetime(2026, 1, 4, 8, 0, tzinfo=timezone.utc),
        "mentioned_symbols": ["SPRK"],
    }

    assert repo.insert_articles([row]) == 1
    assert repo.get_all()[0]["url"] == "https://example.com/c"


def test_link_symbols_is_idempotent(repo, sample_articles):
    repo.insert_articles(sample_articles)
    article_id = repo.get_id_by_url("https://example.com/a")

    repo.link_symbols(article_id, ["AAPL", "MSFT"])
    repo.link_symbols(article_id, ["AAPL", "MSFT"])  # re-run of the transform

    assert len(repo.get_by_symbol("AAPL")) == 1
    assert len(repo.get_by_symbol("MSFT")) == 1


def test_link_symbols_with_no_symbols_is_a_noop(repo, sample_articles):
    repo.insert_articles(sample_articles)
    article_id = repo.get_id_by_url("https://example.com/a")

    repo.link_symbols(article_id, [])

    assert repo.get_by_symbol("AAPL") == []


def test_bulk_link_symbols_dedupes_within_the_batch(repo, sample_articles):
    repo.insert_articles(sample_articles)
    ids = repo.get_ids_by_urls([a["url"] for a in sample_articles])

    links = [
        {"article_id": ids["https://example.com/a"], "symbol": "AAPL"},
        {"article_id": ids["https://example.com/a"], "symbol": "AAPL"},
        {"article_id": ids["https://example.com/b"], "symbol": "AAPL"},
    ]
    repo.bulk_link_symbols(links)

    assert len(repo.get_by_symbol("AAPL")) == 2


def test_get_by_symbol_returns_newest_first(repo, sample_articles):
    repo.insert_articles(sample_articles)
    ids = repo.get_ids_by_urls([a["url"] for a in sample_articles])
    repo.bulk_link_symbols(
        [{"article_id": aid, "symbol": "AAPL"} for aid in ids.values()]
    )

    urls = [a["url"] for a in repo.get_by_symbol("AAPL")]

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


# ---------------------------------------------------------------------------
# published_at handling — REPO_REVIEW #4
# ---------------------------------------------------------------------------


def test_insert_articles_drops_undated_articles(repo):
    """``published_at`` is NOT NULL, and extractors do emit None.

    Dropping these here is what keeps one malformed feed entry from failing the
    whole batch with an IntegrityError.
    """
    rows = [
        {
            "url": "https://example.com/dated",
            "ingest_source": "test",
            "published_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        },
        {"url": "https://example.com/undated", "ingest_source": "test",
         "published_at": None},
        {"url": "https://example.com/missing-key", "ingest_source": "test"},
    ]

    assert repo.insert_articles(rows) == 1
    assert [a["url"] for a in repo.get_all()] == ["https://example.com/dated"]


def test_insert_articles_all_undated_is_a_noop(repo):
    rows = [{"url": "https://example.com/x", "ingest_source": "test",
             "published_at": None}]

    assert repo.insert_articles(rows) == 0
    assert repo.get_all() == []


def test_published_at_is_returned_timezone_aware(repo, sample_articles):
    """SQLite has no timestamptz; UTCDateTime must restore awareness anyway.

    Without this, the same row reads back aware on Postgres and naive on SQLite,
    and any comparison between the two raises TypeError.
    """
    repo.insert_articles(sample_articles)

    for article in repo.get_all():
        assert article["published_at"].tzinfo is not None
        assert article["created_at"].tzinfo is not None


def test_naive_published_at_is_normalised_to_utc(repo):
    """A naive value is assumed UTC rather than rejected."""
    repo.insert_articles(
        [{
            "url": "https://example.com/naive",
            "ingest_source": "test",
            "published_at": datetime(2026, 1, 2, 9, 30),  # no tzinfo
        }]
    )

    stored = repo.get_all()[0]["published_at"]
    assert stored == datetime(2026, 1, 2, 9, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Symbol normalisation
# ---------------------------------------------------------------------------


def test_link_symbols_uppercases_and_dedupes(repo, sample_articles):
    """article_securities has CHECK (symbol = upper(symbol)).

    Case-folding here is what stops a join to market.daily_bars missing purely
    because two pipelines disagreed about capitalisation.
    """
    repo.insert_articles(sample_articles)
    article_id = repo.get_id_by_url("https://example.com/a")

    repo.link_symbols(article_id, ["aapl", "AAPL", " AaPl "])

    assert len(repo.get_by_symbol("AAPL")) == 1


def test_get_by_symbol_accepts_lowercase_input(repo, sample_articles):
    repo.insert_articles(sample_articles)
    article_id = repo.get_id_by_url("https://example.com/a")
    repo.link_symbols(article_id, ["MSFT"])

    assert len(repo.get_by_symbol("msft")) == 1


def test_link_symbols_ignores_blank_entries(repo, sample_articles):
    repo.insert_articles(sample_articles)
    article_id = repo.get_id_by_url("https://example.com/a")

    repo.link_symbols(article_id, ["", "   ", None])

    assert repo.get_by_symbol("AAPL") == []


def test_link_symbols_records_provenance(repo, sample_articles):
    """link_source distinguishes a feed-supplied symbol from an inferred one."""
    from sqlalchemy import select

    from findata.models import ArticleSecurity

    repo.insert_articles(sample_articles)
    a_id = repo.get_id_by_url("https://example.com/a")
    b_id = repo.get_id_by_url("https://example.com/b")

    repo.link_symbols(a_id, ["AAPL"], link_source="extractor")
    repo.link_symbols(b_id, ["MSFT"], link_source="entity_transform")

    with repo.engine.connect() as conn:
        rows = dict(
            conn.execute(
                select(ArticleSecurity.symbol, ArticleSecurity.link_source)
            ).all()
        )

    assert rows == {"AAPL": "extractor", "MSFT": "entity_transform"}


# ---------------------------------------------------------------------------
# Transform bookkeeping
# ---------------------------------------------------------------------------


def test_untransformed_shrinks_as_articles_are_marked(repo, sample_articles):
    repo.insert_articles(sample_articles)

    assert repo.count_untransformed("sentiment") == 2

    first = repo.get_untransformed("sentiment", limit=1)
    assert len(first) == 1
    repo.mark_transformed([first[0]["id"]], "sentiment")

    assert repo.count_untransformed("sentiment") == 1


def test_mark_transformed_is_idempotent(repo, sample_articles):
    """A re-run of a partially-failed batch must not violate the composite PK."""
    repo.insert_articles(sample_articles)
    ids = [a["id"] for a in repo.get_all()]

    repo.mark_transformed(ids, "sentiment")
    repo.mark_transformed(ids, "sentiment")

    assert repo.count_untransformed("sentiment") == 0


def test_transforms_are_tracked_independently(repo, sample_articles):
    """Marking one transform must not mark another."""
    repo.insert_articles(sample_articles)
    ids = [a["id"] for a in repo.get_all()]

    repo.mark_transformed(ids, "sentiment")

    assert repo.count_untransformed("sentiment") == 0
    assert repo.count_untransformed("entity_extraction") == 2


def test_null_score_is_not_retried(repo, sample_articles):
    """A scored-but-unusable article stays scored.

    This is the whole reason article_transforms records the attempt rather than
    the result: without it, every empty-content article is rescored forever.
    """
    repo.insert_articles(sample_articles)
    ids = [a["id"] for a in repo.get_all()]

    repo.update_sentiment_scores([{"id": i, "sentiment_score": None} for i in ids])
    repo.mark_transformed(ids, "sentiment")

    assert repo.count_untransformed("sentiment") == 0
    assert all(a["sentiment_score"] is None for a in repo.get_all())


def test_update_sentiment_scores_writes_values(repo, sample_articles):
    repo.insert_articles(sample_articles)
    ids = sorted(a["id"] for a in repo.get_all())

    repo.update_sentiment_scores(
        [{"id": ids[0], "sentiment_score": 0.8},
         {"id": ids[1], "sentiment_score": -0.6}]
    )

    scores = {a["id"]: a["sentiment_score"] for a in repo.get_all()}
    assert scores[ids[0]] == pytest.approx(0.8)
    assert scores[ids[1]] == pytest.approx(-0.6)
