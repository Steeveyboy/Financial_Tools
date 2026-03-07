# Copilot Instructions

## Repository Overview

This is a multi-project Python repository of independent financial tools. Each subdirectory is a self-contained project with its own dependencies and setup — there is no shared virtual environment or top-level package.

## Projects

| Directory | Type | Key Tech |
|-----------|------|----------|
| `SentimentAnalysis/` | Flask web app | Flask, NLTK, scikit-learn, requests-html |
| `FinancialWebScrapers/` | Scripts + Jupyter notebooks | Requests, Pydantic, pymongo, Pandas |
| `SP500_Analysis/` | Jupyter notebooks | Pandas, yfinance, Matplotlib |
| `descriptions/` | Jupyter notebooks | Pandas, yfinance |

## Architecture

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
