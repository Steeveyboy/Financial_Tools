# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a multi-project Python repository of independent financial tools ("Resonance Desk" data warehouse). Each subdirectory is a self-contained project — there is no shared virtual environment or top-level package. The active development focus is `news_articles/`.

## Projects

| Directory | Type | Key Tech |
|-----------|------|----------|
| `news_articles/` | ETL pipeline (active) | SQLAlchemy, feedparser, HuggingFace datasets |
| `SentimentAnalysis/` | Flask web app | Flask, NLTK, scikit-learn, requests-html |
| `FinancialWebScrapers/` | Scripts + Jupyter notebooks | Requests, Pydantic, pymongo, Pandas |
| `SP500_Analysis/` | Jupyter notebooks | Pandas, yfinance, Matplotlib |
| `descriptions/` | Jupyter notebooks | Pandas, yfinance |

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
export DB_URL="sqlite:///resonance.db"   # or postgresql://...
```

Run the pipeline from the project root (`Financial_Tools/`), not from inside `news_articles/`.

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
| `DB_URL` | `news_articles` | SQLAlchemy URL; required |
| `NEWS_LOG_LEVEL` | `news_articles` | Default: `INFO` |

Place these in a `.env` file at the project root — `news_articles/config.py` calls `load_dotenv()` automatically.
