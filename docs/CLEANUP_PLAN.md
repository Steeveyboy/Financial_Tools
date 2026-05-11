# Repo Cleanup Plan — Financial Data Warehouse

Status: **proposed** (decisions captured below; no code changed yet)

## Goal

Turn this repo from a loose collection of scripts/notebooks into one financial
data warehouse: timeseries market pricing + company information + timeseries
news, all loaded into a single Postgres database, with **one** obvious place
that defines every data model and every table.

## Decisions made

| Question | Decision |
|---|---|
| Unified package name | `findata/` at repo root |
| SEC / XBRL filing data (currently MongoDB) | **Migrate fully to Postgres** — model filings/facts relationally; drop MongoDB |
| Legacy `SentimentAnalysis/` Flask app | Keep functional, just **isolate** it (mark legacy, stop committing its `.venv`) — not folded into the warehouse for now |
| Rollout | Write this plan first; then execute in PR-sized phases below |

## Current state (the mess we're fixing)

### Data sources and where each one writes today

| Source | Lives in | Storage today | Tables / collections | Schema defined as |
|---|---|---|---|---|
| News (Reuters RSS + FNSPID dataset) | `news_articles/` | Postgres/SQLite (`DATABASE_URL`) | `articles`, `article_tickers` | SQLAlchemy **Core** `Table`/`MetaData` (`db/schema.py`) |
| Company profiles (yfinance `info`) | `corporate_db/` (fed by `descriptions/populate_db.py`) | Postgres/SQLite (`DATABASE_URL`) | `exchanges`, `companies`, `insiders` (stub) | SQLAlchemy **2.0 ORM** + **Alembic** |
| Market prices (yfinance OHLCV) | `market_data/fetch_stock_data.py` | Postgres/SQLite (`DATABASE_URL`) | `daily_ohlcv` | **Raw `CREATE TABLE` string** + `pandas.to_sql` |
| SEC filings / XBRL income statements | `FinancialWebScrapers/` | **MongoDB** (`finance_database` / `company-facts`) | `company-facts` collection | **Pydantic** + JSON tag maps in `dataModels/` |
| News sentiment (legacy) | `SentimentAnalysis/` | none — in-memory, renders HTML | — | pickled scikit-learn pipeline |

### Problems

1. **Three DB idioms for one database** — Core tables (news), ORM+Alembic (corporate), raw SQL strings (market). Nothing ties them together; no single `metadata` knows all the tables.
2. **No single artifact describing the warehouse** — `corporate_db/db/schema.sql` covers 3 tables; the article schema is a docstring; the OHLCV schema is a Python constant.
3. **`descriptions/`** is half-migrated — `populate_db.py` correctly writes into `corporate_db`, but sits next to notebooks and an append-only concatenated-JSON file (`company_info.json`).
4. **`SentimentAnalysis/`** duplicates the news-ingestion concept with its own scrapers and committed `.venv`.
5. **`FinancialWebScrapers/`** is an island — MongoDB + Pydantic, never touches the warehouse.
6. **Hygiene** — `.venv/` and `SentimentAnalysis/.venv/` committed; `.env` and `market_data/.env` committed (secrets in git); `README.md` / `CLAUDE.md` stale (`CLAUDE.md` says `DB_URL`, code uses `DATABASE_URL`; references `SP500_Analysis/` which is gone); ~10 feature branches, several already merged; 5 separate `requirements.txt`; notebooks scattered across 5 dirs + `.ipynb_checkpoints`.

## Target structure

```
findata/
  config.py              # the ONE config: DATABASE_URL, log level, ECHO_SQL
  db/
    base.py              # THE single SQLAlchemy DeclarativeBase
    session.py           # get_engine / get_session  (lifted from corporate_db/db/connection.py)
    migrations/          # ONE Alembic tree covering every table in the warehouse
  models/                # one ORM model file per table — THIS is the data model
    exchange.py          # exchanges
    company.py           # companies
    daily_ohlcv.py       # daily_ohlcv          (ported from market_data raw SQL)
    article.py           # articles             (ported from news_articles Core table)
    article_ticker.py    # article_tickers
    filing.py            # filings              (ported from FinancialWebScrapers/Mongo)
    financial_fact.py    # financial_facts      (relational projection of XBRL data)
  sources/               # extract/transform logic ONLY — no schema definitions here
    corporate/           # was corporate_db seeding + descriptions/populate_db.py
    market/              # was market_data/  (keeps pandas bulk insert, targets the ORM table)
    news/                # was news_articles/  extractors + transformers + repository
    sec/                 # was FinancialWebScrapers/  scrapers + XBRL parsing → Postgres
  cli.py                 # unified entry points (or keep a Makefile)

legacy/
  SentimentAnalysis/     # moved here as-is; functional, not part of the warehouse

notebooks/               # all exploratory notebooks consolidated here

docs/
  DATA_MODEL.md          # one section per source: what it ingests, which tables, the PK/dedup key
  schema.sql             # generated from findata.db.base.Base.metadata — every table, kept in sync
```

Key invariant: **every table is an ORM model under `findata/models/` inheriting the one `Base`.** `Base.metadata` is then the authoritative list of warehouse tables, `alembic upgrade head` builds the whole thing, and `make schema` regenerates `docs/schema.sql` from it.

### Proposed warehouse tables (post-migration)

| Table | Source module | Grain / PK | Notes |
|---|---|---|---|
| `exchanges` | corporate | `id`; unique `code` | Seeded (NYSE, NASDAQ, TSX, TSXV) |
| `companies` | corporate | `id`; unique `(ticker, exchange_id)` | yfinance profile fields; FTS on name+description |
| `daily_ohlcv` | market | `(ticker, date)` | Daily OHLCV; consider FK `ticker` → `companies` later |
| `articles` | news | `id`; unique `url` | Headline/body/timestamps; gets `sentiment_score` |
| `article_tickers` | news | `(article_id, ticker)` | M:N article↔company |
| `filings` | sec | `id`; unique `(cik, accession_no)` | One row per SEC submission (raw metadata) |
| `financial_facts` | sec | `(cik, tag, fiscal_period, unit)` or surrogate | Relational projection of XBRL income-statement values |

(Exact columns for `filings` / `financial_facts` to be designed in Phase 6 from the existing Pydantic models + `dataModels/dataModelV3_Income.json`.)

## Execution phases (each ≈ one PR)

### Phase 0 — Hygiene (low risk, do first)
- `git rm -r --cached .venv SentimentAnalysis/.venv`; confirm `.gitignore` covers them.
- `git rm --cached .env market_data/.env`; add `.env.example` at repo root.
- Fix `README.md` + `CLAUDE.md` to match reality (`DATABASE_URL` not `DB_URL`; list current modules; drop `SP500_Analysis`).
- Move all notebooks under `notebooks/`; delete `.ipynb_checkpoints`.
- Prune merged/stale local branches (keep what's genuinely in flight).

### Phase 1 — Scaffold `findata/db`
- Create `findata/` package; lift `corporate_db/db/connection.py` → `findata/db/session.py` and `corporate_db/models/base.py` → `findata/db/base.py`.
- Create `findata/config.py` (single config; `DATABASE_URL`, `LOG_LEVEL`, `ECHO_SQL`).
- Set up **one** Alembic tree at `findata/db/migrations/` with an initial migration covering the current corporate tables.
- Move `corporate_db/models/*` → `findata/models/` unchanged (re-pointed at the new `Base`). `corporate_db/` becomes a thin shim or is removed.

### Phase 2 — Port news tables to ORM
- Convert `news_articles/db/schema.py` Core `Table`s → ORM models `findata/models/article.py`, `article_ticker.py`.
- `news_articles` repository switches to ORM sessions from `findata.db.session`.
- One Alembic migration adds `articles` + `article_tickers` (+ `sentiment_score` column / `transform_log` if we do it now).
- Move `news_articles/` extractor + transformer code under `findata/sources/news/`.

### Phase 3 — Port market data to ORM
- Replace `market_data`'s `CREATE_TABLE_SQL` with ORM model `findata/models/daily_ohlcv.py`; one migration.
- Rewrite `fetch_stock_data.py` against `findata.db.session` (keep the `pandas.to_sql` bulk path, just target the ORM-defined table). Move under `findata/sources/market/`.

### Phase 4 — Fold in `descriptions/`
- Move `descriptions/populate_db.py` into `findata/sources/corporate/` (the yfinance-profile loader).
- Archive `descriptions/*.ipynb` to `notebooks/`; drop `company_info.json` from version control (or keep one sample).

### Phase 5 — Isolate `SentimentAnalysis/`
- Move the directory to `legacy/SentimentAnalysis/` as-is; keep it runnable.
- Remove its committed `.venv`; leave its own `requirements.txt`.
- Add a short note in its README: "legacy, not part of the warehouse."

### Phase 6 — Migrate SEC/XBRL to Postgres
- Design `filings` + `financial_facts` ORM models from the existing Pydantic models and `dataModels/dataModelV3_Income.json`.
- Rewrite `scrape_submissions.py` / `helpful.py` to write into Postgres via `findata.db.session` instead of MongoDB. Move under `findata/sources/sec/`.
- One Alembic migration. MongoDB dependency (`pymongo`) dropped.
- Keep the XBRL tag-map JSON files as data assets under `findata/sources/sec/`.

### Phase 7 — Documentation + unified entry point
- `make schema` target: regenerate `docs/schema.sql` from `findata.db.base.Base.metadata` (Postgres dialect).
- Write `docs/DATA_MODEL.md`: one section per source — what it ingests, which table(s) it writes, the dedup/primary key, refresh cadence — plus a mermaid ER diagram.
- One Makefile: `make migrate`, `make schema`, `make ingest-market TICKERS=...`, `make ingest-news`, `make ingest-corporate`, `make ingest-sec`.
- Collapse the per-project `requirements.txt` into one `pyproject.toml` with optional extras (`[news]`, `[sec]`); `legacy/SentimentAnalysis/` keeps its own.

## Open items to decide during execution
- `filings` / `financial_facts` exact column design (Phase 6).
- Whether `daily_ohlcv.ticker` and `article_tickers.ticker` should become real FKs to `companies` (requires companies to be loaded first — coupling vs. integrity tradeoff).
- Whether to keep a Makefile or a Python `findata/cli.py` (or both).
- Fate of `corporate_db/` after Phase 1 — delete vs. keep as a deprecated shim for one release.
