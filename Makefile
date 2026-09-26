.PHONY: help news news-fnspid article-stats market-data corporate-db sentiment


# Default target
help:
	@echo "Financial Tools — available targets:"
	@echo ""
	@echo "  make news                          Run RSS news extraction (default extractors)"
	@echo "  make news-fnspid TICKERS='AAPL'    Run FNSPID (HuggingFace) extraction for tickers"
	@echo "  make article-stats                 Print aggregate statistics for the articles table"
	@echo "  make market-data TICKERS='AAPL MSFT'  Fetch and store OHLCV data"
	@echo "  make corporate-db                  Initialise / seed the corporate DB schema"
	@echo "  make sentiment                     Start the SentimentAnalysis Flask app (port 5151)"
	@echo ""
	@echo "  DATABASE_URL must be set in the environment or in .env before running any target."
	@echo "  Example: export DATABASE_URL='postgresql://user:pass@localhost:5432/resonance'"

# ── News articles ────────────────────────────────────────────────────────────

news:
	uv run load_news_articles.py --rss $(ARGS)

# Usage: make news-fnspid TICKERS="AAPL MSFT" [ARGS="--start-date 2020-01-01"]
news-fnspid:
	uv run python -m load_news_articles --fnspid

article-stats:
	uv run python -m findata.sources.news.stats

# ── Market data ──────────────────────────────────────────────────────────────

# Usage: make market-data TICKERS="AAPL MSFT" [ARGS="--mode append"]
market-data: ARGS ?= --tickers tickers.json --mode append
market-data:
	uv run python -m findata.sources.market.fetch_stock_data $(ARGS)

# ── Corporate DB ─────────────────────────────────────────────────────────────

corporate-db:
	uv run python -m findata

# ── SentimentAnalysis ────────────────────────────────────────────────────────

sentiment:
	cd SentimentAnalysis && python app.py
