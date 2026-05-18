# Financial Tools — Resonance Desk

A Python project building a single Postgres-backed financial data warehouse that combines:

- **Timeseries market pricing** (daily OHLCV)
- **Company information** (profiles, exchanges, sector / industry / classification)
- **Timeseries news** (Reuters RSS + FNSPID historical dataset)
- **SEC filings** (XBRL income-statement data — migrating to Postgres in Phase 6)

The repository is mid-consolidation. See [`docs/CLEANUP_PLAN.md`](docs/CLEANUP_PLAN.md) for the target structure (one `findata/` package, one ORM `Base`, one Alembic history) and the phased rollout.

## Current modules

| Module | Role | Storage | Notes |
|---|---|---|---|
| [`findata/`](findata/) | Warehouse package — ORM `Base`, models, Alembic tree, and source ETL packages under `findata/sources/` | Postgres / SQLite | Tables: `exchanges`, `companies`, `insiders`, `articles`, `article_tickers`. SQLAlchemy 2.0 ORM + Alembic |
| [`findata/sources/news/`](findata/sources/news/) | News ETL — RSS + FNSPID extractors, sentiment / entity transformer stubs | (writes to findata) | `ArticleRepository` over the `articles` / `article_tickers` ORM models |
| [`market_data/`](market_data/) | Daily OHLCV loader (yfinance) | Postgres / SQLite | Table: `daily_ohlcv` (Phase 3: port to ORM) |
| [`descriptions/`](descriptions/) | yfinance profile loader that populates `findata` | (writes to findata) | `populate_db.py` (Phase 4: fold into `findata/sources/corporate/`) |
| [`SentimentAnalysis/`](SentimentAnalysis/) | Legacy Flask demo app | none | Kept functional; will move to `legacy/` in cleanup Phase 5 |
| [`notebooks/`](notebooks/) | Exploratory Jupyter notebooks | — | Throwaway exploration, not imported by pipeline code |

## Setup

```bash
# from repo root
python -m venv .venv && source .venv/bin/activate
pip install -r findata/requirements.txt \
            -r findata/sources/news/requirements.txt \
            -r market_data/requirements.txt

cp .env.example .env
# edit .env to set DATABASE_URL
```

## Running the pipelines

```bash
make help                                # list available targets

make news                                # RSS news extraction
make news-fnspid TICKERS="AAPL MSFT"     # FNSPID historical news
make market-data TICKERS="AAPL MSFT"     # daily OHLCV
make corporate-db                        # init / seed corporate schema (python -m findata)
alembic upgrade head                     # apply DB migrations (the production path)
make sentiment                           # legacy Flask app (port 5151)
```

`DATABASE_URL` must be set in `.env` or the shell environment before any pipeline runs. PostgreSQL and SQLite are both supported.

## Repository structure

```
Financial_Tools/
├── findata/                # Warehouse package — ORM Base, models, Alembic, source ETL packages
│   ├── db/                 #   session + Alembic tree
│   ├── models/             #   one ORM model per table (Base.metadata)
│   └── sources/
│       └── news/           #   News ETL — extractors, transformers, ArticleRepository
├── market_data/            # Daily OHLCV loader (Phase 3: pending port)
├── descriptions/           # yfinance profile loader (Phase 4: pending fold-in)
├── SentimentAnalysis/      # Legacy Flask app (Phase 5: move to legacy/)
├── notebooks/              # Exploratory notebooks
├── docs/                   # Plans + generated schema reference
├── load_news_articles.py   # News ETL entry point
├── alembic.ini             # Alembic config (points at findata/db/migrations)
└── Makefile                # Common targets
```
