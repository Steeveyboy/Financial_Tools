# Financial Web Scrapers

Python scripts and Jupyter notebooks for scraping financial data from SEC EDGAR, including company submissions, XBRL facts, and income statement modeling.

## Features

- Fetch and store SEC EDGAR company submissions in MongoDB
- Parse US-GAAP XBRL data into structured income statements
- Explore SEC filings interactively via Jupyter notebooks

## Tech Stack

- **Data Fetching:** Requests
- **Data Modeling:** Pydantic, Pandas
- **Storage:** MongoDB (via pymongo)
- **Notebooks:** Jupyter

## Key Files

| File | Description |
|------|-------------|
| `scrape_submissions.py` | Scrapes SEC EDGAR submissions for all tickers and stores them in MongoDB |
| `helpful.py` | Utility functions for fetching XBRL company facts and building income statement DataFrames |
| `sec_scraper.ipynb` | Interactive notebook for exploring SEC data |
| `gaap_examination.ipynb` | Notebook for examining US-GAAP attributes |
| `SEC_API.ipynb` | Notebook for working with the SEC API |

## Setup

1. Install dependencies:
   ```bash
   pip install requests pydantic pymongo pandas
   ```

2. Ensure MongoDB is running locally (default: `mongodb://localhost:27017/`)

3. Run the scraper:
   ```bash
   python scrape_submissions.py
   ```
