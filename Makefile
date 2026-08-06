.PHONY: help news news-fnspid market-data corporate-db sentiment

# Default target
help:
	@echo "Financial Tools — available targets:"
	@echo ""
	@echo "  make news                          Run RSS news extraction (default extractors)"
	@echo "  make news-fnspid TICKERS='AAPL'    Run FNSPID (HuggingFace) extraction for tickers"
	@echo "  make market-data TICKERS='AAPL MSFT'  Fetch and store OHLCV data"
	@echo "  make corporate-db                  Initialise / seed the corporate DB schema"
	@echo "  make sentiment                     Start the SentimentAnalysis Flask app (port 5151)"
	@echo ""
	@echo "  DATABASE_URL must be set in the environment or in .env before running any target."
	@echo "  Example: export DATABASE_URL='postgresql://user:pass@localhost:5432/resonance'"

# ── News articles ────────────────────────────────────────────────────────────

news:
	python load_news_articles.py --rss $(ARGS)

# Usage: make news-fnspid TICKERS="AAPL MSFT" [ARGS="--start-date 2020-01-01"]
news-fnspid:
	python load_news_articles.py --fnspid

# ── Market data ──────────────────────────────────────────────────────────────

# Usage: make market-data TICKERS="AAPL MSFT" [ARGS="--mode append"]
market-data:
	@test -n "$(TICKERS)" || (echo "Error: TICKERS is required. Usage: make market-data TICKERS='AAPL MSFT'" && exit 1)
	python -m findata.sources.market.fetch_stock_data $(TICKERS) $(ARGS)

# ── Corporate DB ─────────────────────────────────────────────────────────────

corporate-db:
	python -m findata

# ── SentimentAnalysis ────────────────────────────────────────────────────────

sentiment:
	cd SentimentAnalysis && python app.py
