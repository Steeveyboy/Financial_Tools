# Financial Tools

A collection of Python-based tools for financial analysis, including web scrapers, sentiment analysis, and data exploration notebooks.

## Projects

| Project | Description | Tech Stack |
|---------|-------------|------------|
| [Sentiment Analysis](SentimentAnalysis/) | Flask web app that scrapes news articles and runs sentiment analysis on them using a trained NLP model | Python, Flask, NLTK, scikit-learn |
| [Financial Web Scrapers](FinancialWebScrapers/) | Scripts and notebooks for scraping SEC EDGAR filings, company facts, and financial data | Python, Requests, Pydantic, MongoDB |
| [S&P 500 Analysis](SP500_Analysis/) | Jupyter notebooks for analyzing S&P 500 fundamentals and stock data | Python, Pandas, Matplotlib, yfinance |
| [Description Parsing](descriptions/) | Notebooks for parsing and searching NYSE stock descriptions | Python, yfinance, Pandas |

## Getting Started

Each project has its own setup. See the individual project READMEs linked above for installation and usage instructions.

### Prerequisites

- Python 3.8+
- pip

## Repository Structure

```
Financial_Tools/
├── SentimentAnalysis/       # News sentiment analysis web app
├── FinancialWebScrapers/    # SEC EDGAR scrapers and financial data tools
├── SP500_Analysis/          # S&P 500 data analysis notebooks
└── descriptions/            # Stock description parsing notebooks
```
