# Copilot Instructions

## Repository Overview

This is a Python repository being consolidated into a single Postgres-backed financial data warehouse ("Resonance Desk"). The end goal is one package (`findata/`) with one ORM `Base`, one Alembic history, and one set of ingestion sources under `findata/sources/`. See [`docs/CLEANUP_PLAN.md`](../docs/CLEANUP_PLAN.md) for the target structure and phased rollout.

The active development focus is the news source under `findata/sources/news/`.

## Projects

| Directory | Type | Key Tech |
|-----------|------|----------|
| `findata/` | Warehouse package — ORM `Base`, models, Alembic tree, source ETL | SQLAlchemy 2.0 ORM + Alembic |
| `findata/sources/news/` | News ETL (active focus) | SQLAlchemy 2.0 ORM, feedparser, HuggingFace datasets |
| `market_data/` | Stock price fetcher (Phase 3: pre-port) | yfinance, raw SQL + pandas |
| `descriptions/` | yfinance profile loader (Phase 4: pre-fold) | Pandas, yfinance |
| `SentimentAnalysis/` | Legacy Flask web app (Phase 5: move to `legacy/`) | Flask, NLTK, scikit-learn |
| `notebooks/` | Exploratory Jupyter notebooks | Pandas, yfinance, Matplotlib |

## Architecture

### findata.sources.news (active focus)

Two-phase ETL pipeline — transforms can be re-run retroactively without re-fetching:

```
Phase 1 — Extraction:  Extractor(s) → ArticleRepository.insert_articles() → articles / article_tickers tables
Phase 2 — Transform:   articles table → Transformer(s) → sentiment_score column / article_tickers table
```

Key design points:
- `articles` / `article_tickers` are ORM models in `findata.models` (`Article`, `ArticleTicker`). `findata/sources/news/db/repository.py` (`ArticleRepository`) is the sole SQL layer — never write raw SQL outside it.
- `ArticleRepository()` with no args falls back to `findata.db.session.get_engine()` so callers can just construct it against the configured `DATABASE_URL`.
- `article_tickers` has a composite primary key `(article_id, ticker)`. Inserts use dialect-aware `INSERT … ON CONFLICT DO NOTHING` (Postgres + SQLite) — keeps transforms idempotent on re-run.
- `ArticleExtractor` subclasses define `source_id` and `extract() -> list[dict]`. URL is the deduplication key.
- If an extractor dict includes `mentioned_tickers`, the pipeline links them at load time (no `EntityTransformer` needed).
- `TransformationPipeline._persist()` has a branch for each `transform_id` — add persistence logic there when implementing a new transformer.

### findata (warehouse)

- `findata/db/base.py` — the one `DeclarativeBase`. Every table is an ORM model under `findata/models/` inheriting it.
- `findata/db/session.py` — `get_engine()`, `get_session()`, `init_db()`.
- `findata/db/migrations/` — the single Alembic tree; `alembic.ini` is at the repo root.
- `findata/config.py` — `DATABASE_URL` / `ECHO_SQL` from `.env`.
- `python -m findata` runs `init_db()` (dev convenience); `alembic upgrade head` is the production path.

### SentimentAnalysis (legacy)

Flask app on port 5151. Not part of the warehouse — slated for `legacy/` in Phase 5. The sentiment model (`sentiment/sentiment_pipeline.pickle`) is loaded at module import time in `webscraperControl.py`; run `app.py` from inside `SentimentAnalysis/`.

---

## Current Known Stubs / TODOs

These are the open implementation tasks. Check GitHub Issues for the latest status.

| # | Location | Description | Priority |
|---|----------|-------------|----------|
| 1 | `findata/sources/news/transformers/sentiment.py` | `SentimentTransformer.transform()` — score articles using FinBERT (recommended) | high |
| 2 | `findata/sources/news/transformers/entity.py` | `EntityTransformer.transform()` — extract ticker mentions using spaCy NER | high |
| 3 | `findata/sources/news/db/repository.py` | `get_untransformed()` — currently returns all articles; needs a `transform_log` table | high |
| 4 | `findata/models/article.py` + new migration | Add `sentiment_score FLOAT` column to `articles` | medium |
| 5 | `findata/sources/news/pipeline.py` | `TransformationPipeline._persist()` — add persistence for `sentiment_score` | medium |
| 6 | `findata/sources/news/` | Unit tests for `ArticleRepository`, extractors, and transformers | medium |
| 7 | `.github/workflows/` | CI/CD workflow (pytest + flake8) | medium |
| 8 | `market_data/` | Phase 3 port to ORM (`findata/models/daily_ohlcv.py`) | low |

---

## How to Implement a New Extractor

1. Create a new file in `findata/sources/news/extractors/` (e.g., `newsapi.py`)
2. Subclass `ArticleExtractor` from `extractors/base.py`
3. Set `source_id` to a unique short string (e.g., `"newsapi"`)
4. Implement `extract() -> list[dict]` returning dicts with at minimum:
   - `url` (str) — canonical URL, used for deduplication
   - `title` (str) — headline
   - `published_at` (datetime) — publication timestamp
   - Optional: `author`, `publisher`, `content` (plain text, no HTML)
5. For large datasets, override `extract_batches()` to yield chunks (see `huggingface.py`)
6. If the source knows which tickers an article mentions, include `mentioned_tickers: list[str]` in each dict — the pipeline links them automatically
7. Register the extractor in `load_news_articles.py` or wherever the pipeline is configured
8. Add any new dependencies to `findata/sources/news/requirements.txt`

## How to Implement a New Transformer

1. Create a new file in `findata/sources/news/transformers/` (e.g., `topic.py`)
2. Subclass `ArticleTransformer` from `transformers/base.py`
3. Set `transform_id` to a unique short string (e.g., `"topic_classification"`)
4. Implement `transform(articles: list[dict]) -> list[dict]`:
   - Receive article dicts (columns from the `articles` table)
   - Add new keys for derived fields (e.g., `article["topic"] = "earnings"`)
   - Handle `None` content gracefully
   - Return the enriched list
5. Add a persistence branch in `TransformationPipeline._persist()` for your `transform_id`
6. If the transform needs a new DB column, add it to the relevant ORM model in `findata/models/` and create a new Alembic migration (`alembic revision -m "..."` from the repo root)
7. Add any new dependencies to `findata/sources/news/requirements.txt`

---

## Testing Conventions

- Tests live in `tests/` at the project root (mirror the package layout, e.g. `tests/findata/sources/news/`)
- Use **pytest** as the test runner
- Use SQLite in-memory (`sqlite://`) for database tests — pass `create_engine("sqlite://")` directly to `ArticleRepository`
- Mock external APIs (RSS feeds, HuggingFace) — don't hit real endpoints in tests
- Run tests: `python -m pytest tests/ -v`
- Run linter: `flake8 findata/`

## How to Run the Pipeline Locally

```bash
# From the project root (Financial_Tools/)
pip install -r findata/requirements.txt -r findata/sources/news/requirements.txt
export DATABASE_URL="sqlite:///resonance.db"

# Run extraction via the entry-point script
python load_news_articles.py

# Or drive the pipeline programmatically:
python -c "
from findata.sources.news.pipeline import ExtractionPipeline
from findata.sources.news.extractors.rss import RSSExtractor

ExtractionPipeline(engine=None, extractors=[RSSExtractor()]).run()
"
```

## Environment Variables

| Variable | Used by | Notes |
|---|---|---|
| `DATABASE_URL` | `findata` (incl. `findata.sources.news`), `market_data` | SQLAlchemy URL; required |
| `NEWS_LOG_LEVEL` | `findata.sources.news` | Default: `INFO` |
| `ECHO_SQL` | `findata` | Truthy → log all SQL; default off |

Place these in a `.env` file at the project root — all modules call `load_dotenv()` automatically. See `.env.example`.

---

## Key Conventions

### SEC EDGAR API (Phase 6, when SEC ingestion returns)

All requests must include a `User-Agent` header identifying the requester:
```python
{"user-agent": "www.jonsteeves.dev jonathonsteeves@cmail.carleton.ca"}
```

### Text Preprocessing (SentimentAnalysis legacy)

`sentiment/model_wraper.preprocess()` lowercases, strips non-alpha characters, and removes NLTK stopwords.

---

## Agent Workflow

This repository uses GitHub Issues to track work. Specialized agents pick up issues based on labels:

- **`agent:coding`** — implementation tasks (new features, stubs, migrations)
- **`agent:testing`** — writing tests, improving coverage
- **`agent:docs`** — documentation, README updates

Each issue body contains an **Agent Instructions** section with:
- Exact file(s) to edit
- Interface contract (what the method must return)
- Which tests to write or update
- Required dependencies or environment variables

See `.github/ISSUE_TEMPLATE/` for the issue formats used.

## Setup

### SentimentAnalysis (legacy)
```bash
cd SentimentAnalysis
pip install -r requirements.txt
python -c "import nltk; nltk.download('stopwords')"  # first time only
python app.py
```
