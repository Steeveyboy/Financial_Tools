# Repo Map — where everything lives

**This file is the navigation source of truth.** If a path in any other document
disagrees with this one, this one wins — and fix the other document.

Last verified: 2026-08-21 (against commit `b675cfb`).

## The 60-second orientation

```
Financial_Tools/
├── findata/                     # THE package. Everything real lives here.
│   ├── config.py                # DATABASE_URL, ECHO_SQL (loads repo-root .env)
│   ├── __main__.py              # `python -m findata` → init_db() (dev only)
│   ├── db/
│   │   ├── base.py              # the ONE DeclarativeBase
│   │   ├── session.py           # get_engine() / get_session() / init_db()
│   │   └── migrations/          # the ONE Alembic tree (alembic.ini is at repo root)
│   ├── models/                  # one file per table; Base.metadata is authoritative
│   └── sources/                 # one package per upstream data source
│       ├── news/                # ACTIVE FOCUS — RSS + FNSPID extract, transforms
│       └── market/              # yfinance OHLCV
├── descriptions/                # yfinance company-profile loader (writes into findata)
├── notebooks/                   # throwaway exploration; never imported by pipeline code
├── SentimentAnalysis/           # LEGACY Flask app — do not work here
├── tests/                       # pytest, in-memory SQLite
├── docs/                        # plans, recipes, discoveries
├── load_news_articles.py        # entry point: extraction
└── transform_news.py            # entry point: transforms
```

## Entry points

| I want to… | Run |
|---|---|
| Create/seed schema for local dev | `python -m findata` |
| Apply migrations (production path) | `alembic upgrade head` (from repo root) |
| Load news from RSS | `python load_news_articles.py --rss` or `make news` |
| Backfill news from FNSPID | `python load_news_articles.py --fnspid` or `make news-fnspid` |
| Run transforms over stored articles | `python transform_news.py` |
| Load OHLCV | `python -m findata.sources.market.fetch_stock_data AAPL MSFT` |
| Run the tests | `python -m pytest` (from repo root) |

Everything is run **from the repo root**. Nothing is `pip install`-ed; imports
resolve because the repo root is on `sys.path` (pytest gets this from
`pyproject.toml`'s `pythonpath = ["."]`).

## Which document answers which question

| Question | Read |
|---|---|
| Where is X? How do I run it? | this file |
| How do I add an extractor / transformer / migration? | [`docs/RECIPES.md`](RECIPES.md) |
| Why is the repo shaped this way, what's the target shape? | [`docs/CLEANUP_PLAN.md`](CLEANUP_PLAN.md) |
| What's known-broken and what should I work on? | [`REPO_REVIEW.md`](../REPO_REVIEW.md) + CLAUDE.md "Current Priorities" |
| How does the news ETL work internally? | [`findata/sources/news/README.md`](../findata/sources/news/README.md) |
| How is sentiment supposed to work? | [`docs/SENTIMENT_TRANSFORM.md`](SENTIMENT_TRANSFORM.md) |
| Something non-obvious a previous agent learned the hard way | [`docs/discoveries/`](discoveries/INDEX.md) |
| Rules of engagement for agents | [`CLAUDE.md`](../CLAUDE.md) |

## False trails — paths that DO NOT exist

These names appear in older docs, docstrings, and git history. They were
renamed. Do not grep for them, do not create them:

| Dead path | Live path | Moved in |
|---|---|---|
| `news_articles/` | `findata/sources/news/` | Cleanup Phase 2 |
| `corporate_db/` | `findata/db/` + `findata/models/` | Cleanup Phase 1 |
| `market_data/` | `findata/sources/market/` | Cleanup Phase 3 |
| `market_data/tickers.json` | `findata/sources/market/tickers.json` | Cleanup Phase 3 |
| `FinancialWebScrapers/` | removed (commit `e8e90a8`); Phase 6 re-adds `findata/sources/sec/` | — |

`docs/schema.sql` is a **stale hand-written snapshot** (pre-`daily_ohlcv`, pre-sentiment).
The authoritative schema is `findata/models/` + the Alembic tree. Never read
`schema.sql` to answer "what columns does this table have".

## Search hygiene

Two `.venv/` trees are checked out in the working directory (`./.venv/` and
`./SentimentAnalysis/.venv/`) holding tens of thousands of files.

- **Use `rg` / the Grep tool** — both respect `.gitignore`, so venvs are excluded automatically.
- **Avoid bare `find .`** — it does not respect `.gitignore` and will bury the
  answer in site-packages. If you must, scope it: `find findata tests docs -type f`.
- `git ls-files` is the cheapest way to enumerate real repo files.

## Invariants worth knowing before you edit

- **No raw SQL outside a repository class.** For news that's
  `findata/sources/news/db/repository.py::ArticleRepository`.
- **One `Base`, one Alembic tree.** A new table means a model file under
  `findata/models/`, an import in `findata/models/__init__.py` (autogenerate
  discovers models through that import), and a migration.
- **URL is the article dedup key**; `article_tickers` has composite PK
  `(article_id, ticker)` and inserts are `ON CONFLICT DO NOTHING`, so
  extraction and transforms are re-runnable.
- **`logging`, never `print()`** — module-level `_logger`.
- **`SentimentAnalysis/` is out of scope.** It is legacy and unrelated to the warehouse.
