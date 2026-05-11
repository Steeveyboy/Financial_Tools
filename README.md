# Financial Tools — Resonance Desk

A Python project building a single Postgres-backed financial data warehouse that combines:

- **Timeseries market pricing** (daily OHLCV)
- **Company information** (profiles, exchanges, sector / industry / classification)
- **Timeseries news** (Reuters RSS + FNSPID historical dataset)
- **SEC filings** (XBRL income-statement data — currently MongoDB, migrating to Postgres)

The repository is mid-consolidation. See [`docs/CLEANUP_PLAN.md`](docs/CLEANUP_PLAN.md) for the target structure (one `findata/` package, one ORM `Base`, one Alembic history) and the phased rollout.

## Current modules

| Module | Role | Storage | Notes |
|---|---|---|---|
| [`news_articles/`](news_articles/) | News ETL pipeline — RSS + FNSPID extractors, sentiment transformer | Postgres / SQLite | Tables: `articles`, `article_tickers` |
| [`corporate_db/`](corporate_db/) | Company / exchange profiles | Postgres / SQLite | Tables: `exchanges`, `companies`, `insiders`. SQLAlchemy 2.0 ORM + Alembic |
| [`market_data/`](market_data/) | Daily OHLCV loader (yfinance) | Postgres / SQLite | Table: `daily_ohlcv` |
| [`descriptions/`](descriptions/) | yfinance profile loader that populates `corporate_db` | (writes to corporate_db) | `populate_db.py` |
| [`FinancialWebScrapers/`](FinancialWebScrapers/) | SEC EDGAR / XBRL scrapers | MongoDB | Will migrate to Postgres in cleanup Phase 6 |
| [`SentimentAnalysis/`](SentimentAnalysis/) | Legacy Flask demo app | none | Kept functional; will move to `legacy/` in cleanup Phase 5 |
| [`notebooks/`](notebooks/) | Exploratory Jupyter notebooks | — | Throwaway exploration, not imported by pipeline code |

## Setup

```bash
# from repo root
python -m venv .venv && source .venv/bin/activate
pip install -r news_articles/requirements.txt \
            -r market_data/requirements.txt \
            -r corporate_db/requirements.txt

cp .env.example .env
# edit .env to set DATABASE_URL
```

## Running the pipelines

```bash
make help                                # list available targets

make news                                # RSS news extraction
make news-fnspid TICKERS="AAPL MSFT"     # FNSPID historical news
make market-data TICKERS="AAPL MSFT"     # daily OHLCV
make corporate-db                        # init / seed corporate schema
make sentiment                           # legacy Flask app (port 5151)
```

`DATABASE_URL` must be set in `.env` or the shell environment before any pipeline runs. PostgreSQL and SQLite are both supported.

## Repository structure

```
Financial_Tools/
├── findata/                # (planned — see docs/CLEANUP_PLAN.md)
├── news_articles/          # News ETL pipeline
├── corporate_db/           # Company / exchange profiles (ORM + Alembic)
├── market_data/            # Daily OHLCV loader
├── descriptions/           # yfinance profile loader
├── FinancialWebScrapers/   # SEC EDGAR scrapers (MongoDB, migrating)
├── SentimentAnalysis/      # Legacy Flask app
├── notebooks/              # Exploratory notebooks
├── docs/                   # Plans + generated schema reference
├── load_news_articles.py   # News ETL entry point
└── Makefile                # Common targets
```
