# Sentiment Transform (Phase 2)

FinBERT scoring for news articles, end to end. Implements REPO_REVIEW #6.

## What was added

| File | Change |
|---|---|
| `findata/models/article.py` | `sentiment_score` column (`Float`, nullable) |
| `findata/models/transform_log.py` | **new** — `TransformLog` model |
| `findata/models/__init__.py` | registers `TransformLog` |
| `findata/db/migrations/versions/0004_sentiment_and_transform_log.py` | **new** — migration `0004` |
| `findata/sources/news/db/repository.py` | real `get_untransformed()`, plus `count_untransformed()`, `mark_transformed()`, `update_sentiment_scores()` |
| `findata/sources/news/transformers/sentiment.py` | FinBERT implementation (was a stub) |
| `findata/sources/news/pipeline.py` | batched/resumable transform loop, `_persist()` sentiment branch |
| `transform_news.py` | **new** — Phase 2 entry point |
| `findata/sources/news/requirements.txt` | `torch` + `transformers` uncommented |

Migration `0005` is deliberately left free for the pgvector work.

## Design decisions

### Score is signed, `[-1.0, 1.0]`

`sentiment_score = P(positive) - P(negative)`. The old stub docstring said
0.0–1.0; this changed on purpose. The analytical goal is testing whether tone
predicts price movement, and signed-and-centred lines up with signed returns —
neutral sits at 0 instead of an arbitrary 0.5 midpoint, so the sign of the
score and the sign of the return compare directly.

Trade-off: "confidently neutral" and "torn between positive and negative" both
collapse to ~0. Both are uninformative for a directional signal, so that's
acceptable. If the distinction ever matters, store the three class
probabilities rather than encoding them in one float.

### `transform_log` records the *attempt*, not the result

A row means "transform X ran on article Y", whatever the outcome. This is what
lets a `NULL` `sentiment_score` mean two different things safely:

- no `transform_log` row → never scored, will be picked up
- `transform_log` row + `NULL` score → scored, but the article had no usable
  text; **not** retried

Without this, every empty-content article gets rescored on every run forever.

Composite PK `(article_id, transform_id)` + dialect-aware
`INSERT … ON CONFLICT DO NOTHING` (same pattern as `article_tickers`) makes it
idempotent, so a partially-failed batch can just be re-run.

### Batched and resumable

`TransformationPipeline.run()` pages through `get_untransformed()` in batches
(default 500), persisting and logging each batch before fetching the next.
FinBERT over the full ~1.9M-row FNSPID set is hours of compute — an
interrupted run must not start over.

On an unhandled batch failure the pipeline logs the error and stops that
transformer **without** writing to `transform_log`, so the batch stays pending
and the next run retries it.

### Label positions read from model config

`_ensure_model()` resolves `positive`/`negative` indices from
`model.config.id2label` rather than assuming an ordering. FinBERT forks order
the three classes differently, and a wrong assumption silently inverts every
score — which is the kind of bug that looks like a real (negative) research
finding.

### Text selection

Headline leads: `f"{title}. {content}"`. The headline is the most tone-dense
part of a financial news item and, being first, survives BERT's 512-token
truncation. Falls back to whichever of title/content exists; `None` if neither.

## Running it

See the "Running it" section commands in the repo README / session notes:

```bash
pip install -r findata/sources/news/requirements.txt   # pulls torch + transformers
alembic upgrade head                                   # applies 0004
python transform_news.py --max-articles 20             # smoke test
python transform_news.py                               # full run
```

`--device cuda` forces GPU; `--model-batch-size` tunes the forward pass
(default 32, raise it on a GPU).

## Verification queries

```sql
-- distribution of scores
SELECT round(sentiment_score::numeric, 1) AS bucket, count(*)
FROM articles WHERE sentiment_score IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- scored vs. skipped vs. pending
SELECT
  count(*) FILTER (WHERE tl.article_id IS NOT NULL AND a.sentiment_score IS NOT NULL) AS scored,
  count(*) FILTER (WHERE tl.article_id IS NOT NULL AND a.sentiment_score IS NULL)     AS no_text,
  count(*) FILTER (WHERE tl.article_id IS NULL)                                       AS pending
FROM articles a
LEFT JOIN transform_log tl
  ON tl.article_id = a.id AND tl.transform_id = 'sentiment';

-- eyeball the extremes — the real correctness check
SELECT sentiment_score, title FROM articles
WHERE sentiment_score IS NOT NULL
ORDER BY sentiment_score DESC LIMIT 10;
```

## Gotchas hit while building this

### Bulk UPDATE must not carry an explicit WHERE

`update_sentiment_scores()` uses SQLAlchemy 2.0 **bulk UPDATE by primary key**:
each param dict carries `id` plus the columns to set, and the statement is a
bare `session.execute(update(Article), params)`.

Adding `.where(Article.id == bindparam(...))` looks equivalent but raises:

```
bulk synchronize of persistent objects not supported when using
bulk update with additional WHERE criteria
```

The ORM session can't synchronize its identity map against a criteria-based
bulk update. Keep the PK in the params and the WHERE clause out.

### The database was never under Alembic control

Prior to this work the schema was built by `init_db()` /
`Base.metadata.create_all()`, so `alembic_version` did not exist and
`alembic upgrade head` tried to run `0001` against live tables
(`DuplicateTable: relation "exchanges" already exists`). Postgres has
transactional DDL, so it rolled back cleanly.

Fix was `alembic stamp 0003` followed by `alembic upgrade head`.
**From here, `alembic upgrade head` should be the only schema path** —
`python -m findata` / `init_db()` is what caused the divergence.

### Autogenerate cannot see event-listener DDL

`alembic check` reported `ix_company_description_fts` as removed. That index is
created by an `after_create` event listener in `models/company.py`, not
declared on the model, so autogenerate compares it against `Base.metadata`,
doesn't find it, and emits a `DROP INDEX` that would destroy the Postgres
full-text search.

`env.py` now defines `include_object()` excluding `ix_company_description_fts`
and `company_fts` (the SQLite FTS5 counterpart). **Any future event-listener
DDL must be added to `_EVENT_CREATED_OBJECTS` there.**

## Known schema drift (pre-existing, not yet repaired)

Surfaced by `alembic check` after stamping. None of it affects the sentiment
transform; all of it predates this work.

| Item | Nature |
|---|---|
| `ix_article_tickers_ticker_pub` vs `ix_article_tickers_ticker_article` | Cosmetic — pre-ORM index name, renamed in `bbc94ba`; same `(ticker, article_id)` columns |
| `articles.published_at` nullable in DB, `NOT NULL` in model | Real — legacy Core table allowed NULL. Check `count(*) WHERE published_at IS NULL` before enforcing |
| `daily_ohlcv.fetched_at` missing in DB | Real — table was created by `market_data` raw SQL, not by migration `0003` (which does define the column), and `stamp 0003` skipped it |

Repair wants its own migration; the revision number depends on what the
pgvector work takes.

## Status

Implemented, migrated, and run successfully against Postgres on 2026-08-21.
