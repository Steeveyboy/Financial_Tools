.PHONY: help news news-fnspid article-stats market-data corporate-db sentiment

# Default target
help: ## Show this help message
	@echo "Financial Tools — available targets:"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_-]+:.*?## / {printf "  make %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "  DATABASE_URL must be set in the environment or in .env before running any target."
	@echo "  Example: export DATABASE_URL='postgresql://user:pass@localhost:5432/resonance'"

# ── News articles ────────────────────────────────────────────────────────────

news: ## Run RSS news extraction (default extractors). ARGS='...' passthrough
	python load_news_articles.py --rss $(ARGS)

# Usage: make news-fnspid TICKERS="AAPL MSFT" [ARGS="--start-date 2020-01-01"]
news-fnspid: ## Run FNSPID (HuggingFace) extraction. Requires TICKERS='AAPL ...'
	@test -n "$(TICKERS)" || (echo "Error: TICKERS is required. Usage: make news-fnspid TICKERS='AAPL MSFT'" && exit 1)
	python load_news_articles.py --fnspid --tickers $(TICKERS) $(ARGS)

article-stats: ## Print aggregate statistics for the articles table
	python article_stats.py

# ── Market data ──────────────────────────────────────────────────────────────

# Usage: make market-data TICKERS="AAPL MSFT" [ARGS="--mode append"]
market-data: ## Fetch and store OHLCV data. Requires TICKERS='AAPL ...'
	@test -n "$(TICKERS)" || (echo "Error: TICKERS is required. Usage: make market-data TICKERS='AAPL MSFT'" && exit 1)
	cd market_data && python fetch_stock_data.py $(TICKERS) $(ARGS)

# ── Corporate DB ─────────────────────────────────────────────────────────────

corporate-db: ## Initialise / seed the corporate DB schema
	python -m corporate_db

# ── SentimentAnalysis ────────────────────────────────────────────────────────

sentiment: ## Start the SentimentAnalysis Flask app (port 5151)
	cd SentimentAnalysis && python app.py
