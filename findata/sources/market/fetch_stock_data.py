"""
fetch_stock_data.py

Fetches daily OHLCV (Open, High, Low, Close, Volume) stock market data
from Yahoo Finance and inserts it into the daily_ohlcv table.

The table is defined by the ORM model findata.models.DailyOHLCV and
created by Alembic — this script no longer issues any DDL. The database
connection is sourced from findata.db.session.get_engine(), which reads
DATABASE_URL via findata.config.

Usage (run from the repo root):
    python -m findata.sources.market.fetch_stock_data AAPL MSFT GOOG
    python -m findata.sources.market.fetch_stock_data AAPL --start 2024-01-01
    python -m findata.sources.market.fetch_stock_data tickers.json --mode truncate
"""

import argparse
import json
import logging
import os
from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

from sqlalchemy import text, select, delete
from sqlalchemy.engine import Engine
from tqdm import tqdm
from findata.db.session import get_engine
from findata.models import DailyOHLCV



_logger = logging.getLogger(__name__)



# ---------------------------------------------------------------------------
# Step 1 — Fetch data from Yahoo Finance
# ---------------------------------------------------------------------------

class StockDataFetcher:
    """Downloads historical OHLCV data for a single ticker from Yahoo Finance."""

    def __init__(self, ticker: str, start: str, end: str):
        self.ticker = ticker
        self.start = start
        self.end = end
        self.data: pd.DataFrame = pd.DataFrame()

    def fetch(self) -> pd.DataFrame:
        """
        Download daily Open, High, Low, Close, and Volume from Yahoo Finance.

        The resulting DataFrame has a DatetimeIndex and the five OHLCV columns.
        A 'ticker' column is added so rows are self-identifying once written
        to the database.

        Returns an empty DataFrame if no data is available for the given range
        or if the download fails.
        """
        _logger.info("[%s] Fetching %s -> %s", self.ticker, self.start, self.end)

        try:
            df: pd.DataFrame | None = yf.download(
                self.ticker,
                start=self.start,
                end=self.end,
                auto_adjust=True,
                progress=False,  # suppress yfinance's own stdout output
            )
            
        except Exception as exc:
            _logger.error("[%s] Download failed: %s", self.ticker, exc)
            return pd.DataFrame()

        if df.empty:
            _logger.warning("[%s] No data returned — skipping", self.ticker)
            return df

        # yfinance may return multi-level columns for a single ticker; flatten them.
        if df.columns.nlevels > 1:
            df.columns = df.columns.droplevel("Ticker")

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()

        # Normalise column names to lowercase to match the database schema.
        df.columns = [c.lower() for c in df.columns]
        df.index.name = "date"
        df["ticker"] = self.ticker

        self.data = df
        _logger.info("[%s] Retrieved %d rows", self.ticker, len(df))
        return df


# ---------------------------------------------------------------------------
# Step 2 — Persist data to the database
# ---------------------------------------------------------------------------

class StockDatabase:
    """
    Manages database connectivity and storage of OHLCV data via SQLAlchemy.

    Because SQLAlchemy supports many backends, the only change required to
    switch databases is the DATABASE_URL connection string:
        PostgreSQL : postgresql://user:pass@host:5432/dbname
        SQLite     : sqlite:///path/to/file.db
        MySQL      : mysql+pymysql://user:pass@host/dbname
    """

    def __init__(self, engine: Engine):
        self.engine: Engine = engine

    def truncate_table(self) -> None:
        """
        Step 2c (optional): Remove all rows from daily_ohlcv before loading.

        Use this when you want a clean reload rather than an incremental append.
        The table structure is preserved; only the data is removed.

        Uses DELETE FROM rather than TRUNCATE for cross-backend compatibility
        (SQLite does not support TRUNCATE).
        """
        with self.engine.begin() as conn:
            
            statement = delete(DailyOHLCV)
            conn.execute(statement)
        _logger.info("Truncated daily_ohlcv — all existing rows removed")

    def insert(self, df: pd.DataFrame) -> None:
        """
        Step 2d: Write an OHLCV DataFrame to the daily_ohlcv table.

        Uses pandas to_sql with 'append' so new rows are added without
        truncating existing data. Rows with dates that already exist in the
        database are skipped to avoid primary key conflicts.
        """
        ticker = df["ticker"].iloc[0]

        # Drop rows that already exist in the database to avoid PK conflicts.
        existing = self._existing_dates(ticker)
        before = len(df)
        df = df[~df.index.isin(existing)]
        skipped = before - len(df)

        if df.empty:
            _logger.info("[%s] All rows already present — nothing to insert", ticker)
            return

        try:
            df.to_sql("daily_ohlcv", self.engine, if_exists="append", index=True)
        except Exception as exc:
            _logger.error("[%s] Insert failed: %s", ticker, exc)
            return

        _logger.info(
            "[%s] Inserted %d rows%s",
            ticker,
            len(df),
            f" (skipped {skipped} existing)" if skipped else "",
        )

    def _existing_dates(self, ticker: str) -> set[date]:
        """Return the set of dates already stored for a given ticker."""
        
        statement = select(DailyOHLCV.date).where(DailyOHLCV.ticker == ticker)
        
        with self.engine.connect() as conn:
            result = conn.execute(statement)
            return {row[0] for row in result}


def parse_tickers(filename: str) -> list[str]:
    """
    Read ticker symbols from a JSON file.

    The file must contain a JSON array of objects, each with a "Ticker" key:

        [{"Ticker": "AAPL", "Company": "Apple Inc.", ...}, ...]

    Args:
        filename: Path to the JSON file. If not absolute, looks in the same directory as this file.

    Returns:
        A list of ticker symbol strings.

    Raises:
        SystemExit: If the file is missing, not valid JSON, or missing "Ticker" keys.
    """
    if not os.path.isabs(filename):
        filename = os.path.join(os.path.dirname(__file__), filename)
    
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        _logger.error("Ticker file not found: %s", filename)
        raise SystemExit(1)
    except json.JSONDecodeError as exc:
        _logger.error("Invalid JSON in %s: %s", filename, exc)
        raise SystemExit(1)

    try:
        tickers = [item["Ticker"] for item in data]
    except (KeyError, TypeError) as exc:
        _logger.error(
            "Expected a list of objects with a 'Ticker' key in %s: %s", filename, exc
        )
        raise SystemExit(1)

    _logger.info("Loaded %d tickers from %s", len(tickers), filename)
    return tickers


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Fetch daily OHLCV stock data and store via SQLAlchemy",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "tickers",
        nargs="+",
        help="Ticker symbols (e.g. AAPL MSFT) or a path to a JSON file of tickers",
    )
    parser.add_argument(
        "--start",
        default=(datetime.now() - timedelta(days=(365*10))).strftime("%Y-%m-%d"),
        help="Start date YYYY-MM-DD (default: 10 years ago)",
    )
    parser.add_argument(
        "--end",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--mode",
        choices=["append", "truncate"],
        default="append",
        help=(
            "append: add new rows, skip existing dates (default).  "
            "truncate: delete all rows before loading."
        ),
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug-level logging",
    )
    return parser.parse_args()

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    # Configure logging before anything else so all messages are visible.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ----------------------------------------------------------------
    # Step 0: Resolve configuration from environment variables and CLI.
    #
    # CLI flags --start and --end override their respective env vars.
    # DATABASE_URL is read exclusively from the environment to keep
    # credentials out of shell history.
    # ----------------------------------------------------------------

    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # If a single argument ending in .json was given, treat it as a ticker file.
    if isinstance(args.tickers[0], str) and args.tickers[0].endswith(".json"):
        _logger.info("Reading tickers from file %s...", args.tickers[0])
        args.tickers = parse_tickers(args.tickers[0])

    # ----------------------------------------------------------------
    # Steps 2a–2c: Ensure database exists, connect, and prepare table.
    # ----------------------------------------------------------------
    db = StockDatabase(get_engine())

    if args.mode == "truncate":
        db.truncate_table()

    # ----------------------------------------------------------------
    # Steps 1 & 2d: Fetch each ticker then write it to the database.
    # Failed tickers are logged and skipped so the batch always completes.
    # ----------------------------------------------------------------
    failed: list[str] = []

    try:
        for ticker in tqdm(args.tickers, desc="Fetching tickers", unit="ticker"):
            try:
                fetcher = StockDataFetcher(ticker, args.start, args.end)
                df = fetcher.fetch()

                if df.empty:
                    continue

                db.insert(df)
            except Exception as exc:
                _logger.error("[%s] Unexpected error — skipping: %s", ticker, exc)
                failed.append(ticker)
    finally:
        pass

    if failed:
        _logger.warning(
            "%d ticker(s) failed: %s", len(failed), ", ".join(failed)
        )


if __name__ == "__main__":
    main()
