# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Python repository being consolidated into a single Postgres-backed financial data warehouse ("Resonance Desk"). The end goal is one package (`findata/`) with one ORM `Base`, one Alembic history, and one set of ingestion sources. See [docs/CLEANUP_PLAN.md](docs/CLEANUP_PLAN.md) for the target structure and phased rollout.

Today the repo is mid-migration: several modules still write to the same `DATABASE_URL` with different ORM idioms. The active development focus is the news source under `findata/sources/news/`.

## Projects

| Directory | Role | Storage | Key Tech |
|-----------|------|---------|----------|
| `findata/` | Warehouse package — single ORM `Base`, models, one Alembic tree; holds the corporate + news tables and the news ETL source | Postgres / SQLite (`exchanges`, `companies`, `insiders`, `articles`, `article_tickers`) | SQLAlchemy 2.0 ORM + Alembic |
| `market_data/` | Daily OHLCV loader (Phase 3: still pre-port) | Postgres / SQLite (`daily_ohlcv`) | yfinance, raw SQL + pandas |
| `descriptions/` | yfinance profile loader for `findata` (Phase 4: still pre-port) | (writes to findata) | Pandas, yfinance |
| `SentimentAnalysis/` | Legacy Flask demo app (Phase 5: move to `legacy/`) | none (in-memory) | Flask, NLTK, scikit-learn |
| `notebooks/` | Exploratory Jupyter notebooks | — | Pandas, yfinance, Matplotlib |

Entry points at the repo root: `load_news_articles.py` (news ETL), `Makefile` (common targets).

## findata.sources.news — News ETL Architecture

The pipeline has two independent phases so transforms can be re-run retroactively without re-fetching:

```
Phase 1 — Extraction:  Extractor(s) → ArticleRepository.insert_articles() → articles / article_tickers tables
Phase 2 — Transform:   articles table → Transformer(s) → sentiment_score column / article_tickers table
```

**Key design points:**
- The `articles` / `article_tickers` tables are ORM models in `findata.models` (`Article`, `ArticleTicker`). `findata/sources/news/db/repository.py` (`ArticleRepository`) drives them through SQLAlchemy 2.0 sessions.
- `ArticleRepository()` falls back to `findata.db.session.get_engine()` when no engine is passed in (so callers can just write `ArticleRepository()` against the configured `DATABASE_URL`).
- `ArticleExtractor` subclasses define `source_id` and `extract() -> list[dict]`. URL is the deduplication key.
- If an extractor dict includes `mentioned_tickers`, the pipeline links them at load time (no EntityTransformer needed).
- `article_tickers` has a composite primary key `(article_id, ticker)`. Inserts use dialect-aware `INSERT … ON CONFLICT DO NOTHING` (Postgres + SQLite) so transforms can be re-run safely.
- `ArticleRepository` is the sole SQL layer — never write raw SQL outside it.
- `get_untransformed()` is a stub that currently returns all articles; a `transform_log` table is the planned fix.
- `TransformationPipeline._persist()` has a TODO branch for each `transform_id` — add persistence logic there when implementing a new transformer.

**Setup:**
```bash
pip install -r findata/sources/news/requirements.txt
export DATABASE_URL="sqlite:///resonance.db"   # or postgresql://...
```

Run the pipeline from the project root (`Financial_Tools/`): `python load_news_articles.py`.

## findata — warehouse package

The target home for the whole warehouse (see `docs/CLEANUP_PLAN.md`). Structure:
- `findata/db/base.py` — the one `DeclarativeBase`. Every table is an ORM model under `findata/models/` inheriting it, so `Base.metadata` is the authoritative table list.
- `findata/db/session.py` — `get_engine()`, `get_session()` (commit/rollback context manager), `init_db()` (create_all + seed default exchanges).
- `findata/db/migrations/` — the single Alembic tree; `alembic.ini` is at the repo root. `env.py` reads `DATABASE_URL` and imports `findata.models` for autogenerate.
- `findata/config.py` — `DATABASE_URL` / `ECHO_SQL`, loads `<repo_root>/.env`.
- `findata/sources/` — extract/transform packages for each upstream source. Currently `findata/sources/news/` (RSS + FNSPID); `market/`, `corporate/`, `sec/` arrive in later phases.

`python -m findata` runs `init_db()` (dev convenience); `alembic upgrade head` is the production path. Currently holds the corporate tables (`exchanges`, `companies`, `insiders`) and the news tables (`articles`, `article_tickers`); market / SEC tables migrate in per the cleanup plan. `companies` has dialect-conditional full-text search (Postgres GIN / SQLite FTS5) — see `models/company.py`.

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

## SEC / XBRL (Phase 6)

`FinancialWebScrapers/` has been removed from the working tree (commit `e8e90a8`). Phase 6 of the cleanup plan re-introduces SEC ingestion under `findata/sources/sec/`, writing directly to Postgres (no MongoDB). The XBRL tag mappings and SEC EDGAR scripts will need to be recovered from git history when that phase begins.

**SEC EDGAR API — required header (for future use):**
```python
{"user-agent": "www.jonsteeves.dev jonathonsteeves@cmail.carleton.ca"}
```

## Environment Variables

| Variable | Used by | Notes |
|---|---|---|
| `DATABASE_URL` | `findata` (incl. `findata.sources.news`), `market_data` | SQLAlchemy URL; required |
| `NEWS_LOG_LEVEL` | `findata.sources.news` | Default: `INFO` |
| `ECHO_SQL` | `findata` | Truthy → log all SQL; default off |
| `START_DATE`, `END_DATE` | `market_data` | Optional `YYYY-MM-DD` defaults for OHLCV fetch |

Place these in a `.env` file at the project root — all modules call `load_dotenv()` automatically. See `.env.example` for the full set.
