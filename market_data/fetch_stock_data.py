"""
fetch_stock_data.py

Fetches daily OHLCV (Open, High, Low, Close, Volume) stock market data
from Yahoo Finance and inserts it into a database via SQLAlchemy.

Configuration (environment variables):
    DB_URL     - SQLAlchemy connection string (required)
                 Examples:
                   postgresql://user:pass@localhost:5432/market_data
                   sqlite:///market_data.db
                   mysql+pymysql://user:pass@localhost/market_data
    START_DATE - Default start date (YYYY-MM-DD), fallback: 2015-01-01
    END_DATE   - Default end date   (YYYY-MM-DD), fallback: today

Usage:
    export DB_URL="postgresql://user:pass@localhost:5432/market_data"
    python fetch_stock_data.py AAPL MSFT GOOG
    python fetch_stock_data.py AAPL --start 2024-01-01
"""

import argparse
import logging
import os
from datetime import datetime

import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from dotenv import load_dotenv


load_dotenv()  # Load environment variables from .env file if present

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _env(key: str, default: str | None = None) -> str | None:
    """Return an environment variable value, falling back to a default."""
    return os.environ.get(key, default)


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

        Returns an empty DataFrame if no data is available for the given range.
        """
        print(f"[{self.ticker}] Fetching {self.start} -> {self.end}...")
        df = yf.download(self.ticker, start=self.start, end=self.end, auto_adjust=True)

        if df.empty:
            print(f"[{self.ticker}]   No data returned — skipping")
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
        print(f"[{self.ticker}]   Retrieved {len(df)} rows")
        return df


# ---------------------------------------------------------------------------
# Step 2 — Persist data to the database
# ---------------------------------------------------------------------------

class StockDatabase:
    """
    Manages database connectivity and storage of OHLCV data via SQLAlchemy.

    Because SQLAlchemy supports many backends, the only change required to
    switch databases is the DB_URL connection string:
        PostgreSQL : postgresql://user:pass@host:5432/dbname
        SQLite     : sqlite:///path/to/file.db
        MySQL      : mysql+pymysql://user:pass@host/dbname
    """

    CREATE_TABLE_SQL = text("""
        CREATE TABLE IF NOT EXISTS daily_ohlcv (
            ticker  VARCHAR(10)    NOT NULL,
            date    DATE           NOT NULL,
            open    NUMERIC(12,4),
            high    NUMERIC(12,4),
            low     NUMERIC(12,4),
            close   NUMERIC(12,4),
            volume  BIGINT,
            PRIMARY KEY (ticker, date)
        )
    """)

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine: Engine | None = None

    def ensure_database(self) -> None:
        """
        Step 2a: Create the target database if it does not already exist.

        Parses the DB_URL to extract the database name, then connects to the
        server's default 'postgres' database to check for (and optionally
        create) the target. This step is only relevant for PostgreSQL; for
        SQLite the file is created automatically, and for other backends the
        database must already exist.
        """
        url = make_url(self.db_url)

        # Only PostgreSQL needs explicit database creation.
        if url.get_backend_name() != "postgresql":
            return

        db_name = url.database
        if not db_name:
            return

        # Connect to the default 'postgres' database to issue CREATE DATABASE.
        admin_url = url.set(database="postgres")
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            ).scalar()

            if not exists:
                # Database names can't be parameterised; validate to prevent injection.
                if not db_name.isidentifier():
                    raise ValueError(f"Invalid database name: {db_name}")
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                print(f"  Created database '{db_name}'")
            else:
                print(f"  Database '{db_name}' already exists")

        admin_engine.dispose()

    def connect(self) -> None:
        """
        Step 2b: Create a SQLAlchemy engine for the configured database URL.

        The engine manages a connection pool automatically; no explicit
        connect/disconnect calls are needed for individual queries.
        """
        print("Connecting to database...")
        self.engine = create_engine(self.db_url)
        print(f"  Engine ready ({self.engine.dialect.name})")

    def ensure_table(self) -> None:
        """
        Step 2c: Create the daily_ohlcv table if it does not already exist.

        The table's composite primary key (ticker, date) guarantees at most
        one OHLCV row per ticker per trading day.
        """
        with self.engine.begin() as conn:
            conn.execute(self.CREATE_TABLE_SQL)
        print("  Table daily_ohlcv is ready")

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
            print(f"[{ticker}]   All rows already present — nothing to insert")
            return

        df.to_sql("daily_ohlcv", self.engine, if_exists="append", index=True)
        print(f"[{ticker}]   Inserted {len(df)} rows" +
              (f" (skipped {skipped} existing)" if skipped else ""))

    def _existing_dates(self, ticker: str) -> set:
        """Return the set of dates already stored for a given ticker."""
        query = text("SELECT date FROM daily_ohlcv WHERE ticker = :ticker")
        with self.engine.connect() as conn:
            result = conn.execute(query, {"ticker": ticker})
            return {row[0] for row in result}

    def dispose(self) -> None:
        """Release all database connections in the engine's pool."""
        if self.engine:
            self.engine.dispose()
            print("  Database connections released")



def parse_tickers(filename: str) -> list[str]:
    """Read a list of ticker symbols from a JSON file."""
    import json
    with open(filename, "r") as f:
        data = json.load(f)
        return [item["Ticker"] for item in data]
    
# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    # ----------------------------------------------------------------
    # Step 0: Resolve configuration from environment variables and CLI.
    #
    # CLI flags --start and --end override their respective env vars.
    # DB_URL is read exclusively from the environment to keep credentials
    # out of shell history.
    # ----------------------------------------------------------------
    db_url = _env("DB_URL")
    if not db_url:
        msg = """Error: DB_URL environment variable is not set.\n
                export DB_URL=\"sqlite:///market_data.db"""
        raise SystemExit(msg)

    parser = argparse.ArgumentParser(
        description="Fetch daily OHLCV stock data and store via SQLAlchemy",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("tickers", nargs="+", help="Ticker symbols, e.g. AAPL MSFT GOOG")
    parser.add_argument(
        "--start",
        default=_env("START_DATE", "2015-01-01"),
        help="Start date YYYY-MM-DD  [env: START_DATE]",
    )
    parser.add_argument(
        "--end",
        default=_env("END_DATE", datetime.now().strftime("%Y-%m-%d")),
        help="End date YYYY-MM-DD    [env: END_DATE]",
    )
    args = parser.parse_args()

    if (type(args.tickers[0]) == str) and (args.tickers[0].endswith(".json")):
        print(f"Reading tickers from file {args.tickers[0]}...")
        args.tickers = parse_tickers(args.tickers[0])
    # ----------------------------------------------------------------
    # Steps 2a–2c: Ensure database exists, connect, and prepare table.
    # ----------------------------------------------------------------
    db = StockDatabase(db_url)
    db.ensure_database()
    db.connect()
    db.ensure_table()

    # ----------------------------------------------------------------
    # Steps 1 & 2d: Fetch each ticker then write it to the database.
    # ----------------------------------------------------------------
    try:
        for ticker in args.tickers:
            fetcher = StockDataFetcher(ticker, args.start, args.end)
            df = fetcher.fetch()

            if df.empty:
                continue

            db.insert(df)
    finally:
        db.dispose()

if __name__ == "__main__":
    main()
