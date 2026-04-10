# Copilot Instructions

## Repository Overview

This is a multi-project Python repository of independent financial tools ("Resonance Desk" data warehouse). Each subdirectory is a self-contained project with its own dependencies and setup — there is no shared virtual environment or top-level package. The active development focus is `news_articles/`.

## Projects

| Directory | Type | Key Tech |
|-----------|------|----------|
| `news_articles/` | ETL pipeline (active) | SQLAlchemy, feedparser, HuggingFace datasets |
| `SentimentAnalysis/` | Flask web app | Flask, NLTK, scikit-learn, requests-html |
| `FinancialWebScrapers/` | Scripts + Jupyter notebooks | Requests, Pydantic, pymongo, Pandas |
| `SP500_Analysis/` | Jupyter notebooks | Pandas, yfinance, Matplotlib |
| `descriptions/` | Jupyter notebooks | Pandas, yfinance |
| `market_data/` | Stock price fetcher | yfinance, SQLAlchemy |
| `pm_agent/` | Project manager agent | PyGithub, PyYAML |

## Architecture

### news_articles (active focus)

Two-phase ETL pipeline — transforms can be re-run retroactively without re-fetching:

```
Phase 1 — Extraction:  Extractor(s) → ArticleRepository.insert_articles() → articles / article_tickers tables
Phase 2 — Transform:   articles table → Transformer(s) → sentiment_score column / article_tickers table
```

Key design points:
- `ArticleExtractor` subclasses define `source_id` and `extract() -> list[dict]`. URL is the deduplication key.
- If an extractor dict includes `mentioned_tickers`, the pipeline links them at load time.
- `ArticleRepository` is the sole SQL layer — never write raw SQL outside it.
- `TransformationPipeline._persist()` has a branch for each `transform_id`.

### SentimentAnalysis
Flask app (port 5151) with this data flow:
1. `webscrapers/reuters.py` and `webscrapers/CBC.py` each return a Pandas DataFrame with columns: `Source`, `title`, `description`, `url`, `image`, `date`, `keyword`
2. `webscrapers/webscraperControl.py` aggregates them and calls `model_wraper.analyse_articles()`, which adds a `sentiment_score` column (0–1 float)
3. `app.py` converts the DataFrame to a list of dicts for the Jinja2 template

**Important:** The sentiment model (`sentiment/sentiment_pipeline.pickle`) is loaded at module import time in `webscraperControl.py`. `app.py` must be run from within the `SentimentAnalysis/` directory.

### FinancialWebScrapers
- `tickers.json` maps ticker symbols to SEC CIK numbers; all scripts read this file
- `scrape_submissions.py` fetches SEC EDGAR submissions and stores them in MongoDB (`finance_database` / `company-facts` collection)
- `helpful.py` fetches US-GAAP XBRL data from SEC and builds income statement DataFrames
- `dataModels/dataModelV3_Income.json` maps human-readable line items (e.g., `"Total revenue"`) to US-GAAP XBRL tag names (e.g., `"Revenues"`)
- `helpful.make_q4()` derives Q4 values by subtracting the sum of Q1–Q3 (10-Q) from the annual total (10-K), because SEC filings only report cumulative YTD figures

---

## Current Known Stubs / TODOs

These are the open implementation tasks. Check GitHub Issues for the latest status.

| # | Location | Description | Priority |
|---|----------|-------------|----------|
| 1 | `news_articles/transformers/sentiment.py` | `SentimentTransformer.transform()` — score articles using FinBERT (recommended) | high |
| 2 | `news_articles/transformers/entity.py` | `EntityTransformer.transform()` — extract ticker mentions using spaCy NER (recommended) | high |
| 3 | `news_articles/db/repository.py` | `get_untransformed()` — currently returns all articles; needs a `transform_log` table | high |
| 4 | `news_articles/db/schema.py` | Add `sentiment_score FLOAT` column to the articles table | medium |
| 5 | `news_articles/pipeline.py` | `TransformationPipeline._persist()` — add persistence for `sentiment_score` | medium |
| 6 | `news_articles/` | Unit tests for `ArticleRepository`, extractors, and transformers | medium |
| 7 | `.github/workflows/` | CI/CD workflow (pytest + flake8) | medium |
| 8 | `market_data/` | Integrate sentiment scores with OHLCV data for correlation analysis | low |

---

## How to Implement a New Extractor

1. Create a new file in `news_articles/extractors/` (e.g., `newsapi.py`)
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
8. Add any new dependencies to `news_articles/requirements.txt`

## How to Implement a New Transformer

1. Create a new file in `news_articles/transformers/` (e.g., `topic.py`)
2. Subclass `ArticleTransformer` from `transformers/base.py`
3. Set `transform_id` to a unique short string (e.g., `"topic_classification"`)
4. Implement `transform(articles: list[dict]) -> list[dict]`:
   - Receive article dicts (columns from the `articles` table)
   - Add new keys for derived fields (e.g., `article["topic"] = "earnings"`)
   - Handle `None` content gracefully
   - Return the enriched list
5. Add a persistence branch in `TransformationPipeline._persist()` for your `transform_id`
6. If the transform needs a new DB column, add it to `news_articles/db/schema.py`
7. Add any new dependencies to `news_articles/requirements.txt`

---

## Testing Conventions

- Tests live in `tests/` at the project root (e.g., `tests/news_articles/`)
- Use **pytest** as the test runner
- Use SQLite in-memory (`sqlite://`) for database tests
- Mock external APIs (RSS feeds, HuggingFace) — don't hit real endpoints in tests
- Run tests: `python -m pytest tests/ -v`
- Run linter: `flake8 news_articles/ pm_agent/`

## How to Run the Pipeline Locally

```bash
# From the project root (Financial_Tools/), NOT from inside news_articles/
pip install -r news_articles/requirements.txt
export DB_URL="sqlite:///resonance.db"

# Run extraction
python load_news_articles.py

# Or use the pipeline programmatically:
python -c "
from sqlalchemy import create_engine
from news_articles.pipeline import ExtractionPipeline
from news_articles.extractors.rss import RSSExtractor

engine = create_engine('sqlite:///resonance.db')
pipeline = ExtractionPipeline(engine, extractors=[RSSExtractor()])
pipeline.run()
"
```

## Environment Variables

| Variable | Used by | Notes |
|---|---|---|
| `DB_URL` | `news_articles`, `market_data` | SQLAlchemy URL; required |
| `NEWS_LOG_LEVEL` | `news_articles` | Default: `INFO` |
| `GITHUB_TOKEN` | `pm_agent` | GitHub PAT for issue/project management |

Place these in a `.env` file at the project root — `news_articles/config.py` calls `load_dotenv()` automatically.

---

## Key Conventions

### SEC EDGAR API
All requests must include a `User-Agent` header identifying the requester:
```python
{"user-agent": "www.jonsteeves.dev jonathonsteeves@cmail.carleton.ca"}
```

### Text Preprocessing (SentimentAnalysis)
`sentiment/model_wraper.preprocess()` lowercases, strips non-alpha characters, and removes NLTK stopwords. Call this before passing text to the model if working outside the pipeline.

### Data Models
XBRL tag mappings live in `FinancialWebScrapers/dataModels/`. The current income statement model is `dataModelV3_Income.json`; balance sheet fields are also defined there.

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

### SentimentAnalysis
```bash
cd SentimentAnalysis
pip install -r requirements.txt
python -c "import nltk; nltk.download('stopwords')"  # first time only
python app.py
```

### FinancialWebScrapers
```bash
pip install requests pydantic pymongo pandas
# Requires MongoDB running at mongodb://localhost:27017/
python scrape_submissions.py
```
