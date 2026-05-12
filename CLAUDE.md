# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Python repository being consolidated into a single Postgres-backed financial data warehouse ("Resonance Desk"). The end goal is one package (`findata/`) with one ORM `Base`, one Alembic history, and one set of ingestion sources. See [docs/CLEANUP_PLAN.md](docs/CLEANUP_PLAN.md) for the target structure and phased rollout.

Today the repo is mid-migration: several independent modules each write to the same `DATABASE_URL` but with different ORM idioms. The active development focus is `news_articles/`.

## Projects

| Directory | Role | Storage | Key Tech |
|-----------|------|---------|----------|
| `news_articles/` | News ETL pipeline (active) | Postgres / SQLite (`articles`, `article_tickers`) | SQLAlchemy Core, feedparser, HuggingFace datasets |
| `findata/` | Warehouse package — single ORM `Base`, models, one Alembic tree. Currently holds the corporate tables | Postgres / SQLite (`exchanges`, `companies`, `insiders`) | SQLAlchemy 2.0 ORM + Alembic |
| `market_data/` | Daily OHLCV loader | Postgres / SQLite (`daily_ohlcv`) | yfinance, raw SQL + pandas |
| `descriptions/` | yfinance profile loader for `findata` | (writes to findata) | Pandas, yfinance |
| `FinancialWebScrapers/` | SEC EDGAR / XBRL scrapers | MongoDB (`finance_database.company-facts`) | Requests, Pydantic, pymongo |
| `SentimentAnalysis/` | Legacy Flask demo app | none (in-memory) | Flask, NLTK, scikit-learn |
| `notebooks/` | Exploratory Jupyter notebooks | — | Pandas, yfinance, Matplotlib |

Entry points at the repo root: `load_news_articles.py` (news ETL), `Makefile` (common targets).

## news_articles — ETL Architecture

The pipeline has two independent phases so transforms can be re-run retroactively without re-fetching:

```
Phase 1 — Extraction:  Extractor(s) → ArticleRepository.insert_articles() → articles / article_tickers tables
Phase 2 — Transform:   articles table → Transformer(s) → sentiment_score column / article_tickers table
```

**Key design points:**
- `ArticleExtractor` subclasses define `source_id` and `extract() -> list[dict]`. URL is the deduplication key.
- If an extractor dict includes `mentioned_tickers`, the pipeline links them at load time (no EntityTransformer needed).
- `ArticleRepository` is the sole SQL layer — never write raw SQL outside it.
- `get_untransformed()` is a stub that currently returns all articles; a `transform_log` table is the planned fix.
- `TransformationPipeline._persist()` has a TODO branch for each `transform_id` — add persistence logic there when implementing a new transformer.

**Setup:**
```bash
pip install -r news_articles/requirements.txt
export DATABASE_URL="sqlite:///resonance.db"   # or postgresql://...
```

Run the pipeline from the project root (`Financial_Tools/`), not from inside `news_articles/`.

## findata — warehouse package

The target home for the whole warehouse (see `docs/CLEANUP_PLAN.md`). Structure:
- `findata/db/base.py` — the one `DeclarativeBase`. Every table is an ORM model under `findata/models/` inheriting it, so `Base.metadata` is the authoritative table list.
- `findata/db/session.py` — `get_engine()`, `get_session()` (commit/rollback context manager), `init_db()` (create_all + seed default exchanges).
- `findata/db/migrations/` — the single Alembic tree; `alembic.ini` is at the repo root. `env.py` reads `DATABASE_URL` and imports `findata.models` for autogenerate.
- `findata/config.py` — `DATABASE_URL` / `ECHO_SQL`, loads `<repo_root>/.env`.

`python -m findata` runs `init_db()` (dev convenience); `alembic upgrade head` is the production path. Currently only the corporate tables (`exchanges`, `companies`, `insiders`) live here; news / market / SEC tables migrate in per the cleanup plan. `companies` has dialect-conditional full-text search (Postgres GIN / SQLite FTS5) — see `models/company.py`.

## SentimentAnalysis

Flask app on port 5151. Data flow: scrapers → `webscraperControl.py` → `model_wraper.analyse_articles()` (adds `sentiment_score` 0–1 column) → `app.py` Jinja2 template.

The sentiment model (`sentiment/sentiment_pipeline.pickle`) loads at import time in `webscraperControl.py`. Run `app.py` from inside `SentimentAnalysis/`.

```bash
cd SentimentAnalysis
pip install -r requirements.txt
python -c "import nltk; nltk.download('stopwords')"  # first time only
python app.py
```

`sentiment/model_wraper.preprocess()` lowercases, strips non-alpha chars, and removes NLTK stopwords. Call it before passing text to the model outside the pipeline.

## FinancialWebScrapers

- `tickers.json` maps ticker symbols to SEC CIK numbers; all scripts read this file.
- `scrape_submissions.py` stores SEC EDGAR data in MongoDB (`finance_database` / `company-facts`). Requires MongoDB at `mongodb://localhost:27017/`.
- `helpful.make_q4()` derives Q4 by subtracting Q1–Q3 (10-Q) from the annual (10-K), because SEC only reports cumulative YTD.
- XBRL tag mappings live in `dataModels/dataModelV3_Income.json` (current income statement model).

**SEC EDGAR API — required header:**
```python
{"user-agent": "www.jonsteeves.dev jonathonsteeves@cmail.carleton.ca"}
```

## Environment Variables

| Variable | Used by | Notes |
|---|---|---|
| `DATABASE_URL` | `news_articles`, `market_data`, `findata` | SQLAlchemy URL; required |
| `NEWS_LOG_LEVEL` | `news_articles` | Default: `INFO` |
| `ECHO_SQL` | `findata` | Truthy → log all SQL; default off |
| `START_DATE`, `END_DATE` | `market_data` | Optional `YYYY-MM-DD` defaults for OHLCV fetch |

Place these in a `.env` file at the project root — all modules call `load_dotenv()` automatically. See `.env.example` for the full set.
