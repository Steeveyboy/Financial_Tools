"""
fetch_stock_data.py

Fetches daily OHLCV (Open, High, Low, Close, Volume) stock market data
from Yahoo Finance and inserts it into the market.daily_bars table.

The table is defined by the ORM model findata.models.DailyBar. On startup
the script creates the market schema and the daily_bars table if either is
missing; existing objects are left untouched. The database connection is
sourced from findata.db.session.get_engine(), which reads DATABASE_URL via
findata.config.

Usage (run from the repo root):
    python -m findata.sources.market.fetch_stock_data AAPL MSFT GOOG
    python -m findata.sources.market.fetch_stock_data AAPL --start 2024-01-01
    python -m findata.sources.market.fetch_stock_data tickers.json --mode truncate
    python -m findata.sources.market.fetch_stock_data -t AAPL MSFT
"""

import argparse
import json
import logging
import os
from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

from sqlalchemy import select, delete
from sqlalchemy.engine import Engine
from tqdm import tqdm
from sqlalchemy import insert as sa_insert

from findata.db.session import create_schemas, get_engine
from findata.models import DailyBar

#: Value written to market.daily_bars.source for every row this module
#: writes. Adjustment methodology differs between providers, so a series
#: must never silently mix them.
SOURCE_NAME = "yfinance"



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

        The resulting DataFrame has a DatetimeIndex named trade_date, the raw
        OHLCV columns, adj_close, and the dividend/split adjustment data.
        A 'symbol' and 'source' column are added so rows are self-identifying
        once written to the database.

        Returns an empty DataFrame if no data is available for the given range
        or if the download fails.
        """
        _logger.info("[%s] Fetching %s -> %s", self.ticker, self.start, self.end)

        try:
            df: pd.DataFrame | None = yf.download(
                self.ticker,
                start=self.start,
                end=self.end,
                # auto_adjust=False is deliberate. With auto_adjust=True (the
                # yfinance default) the Close column is ALREADY adjusted and no
                # Adj Close column is returned — so the warehouse would store
                # adjusted prices in a column named `close` and have no raw
                # price at all. We want both, separately labelled.
                auto_adjust=False,
                # Dividends and Stock Splits, so the adjustment can be
                # recomputed rather than taken on trust.
                actions=True,
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

        # Map yfinance's column names onto the warehouse's. Anything yfinance
        # omits for this symbol is filled below rather than silently missing.
        wanted = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
            "Dividends": "dividend_amount",
            "Stock Splits": "split_coefficient",
        }
        missing = [c for c in wanted if c not in df.columns]
        if missing:
            _logger.warning(
                "[%s] yfinance omitted %s — those columns will be NULL/default",
                self.ticker,
                ", ".join(missing),
            )

        df = df[[c for c in wanted if c in df.columns]].copy()
        df.columns = [wanted[c] for c in df.columns]

        # NOT NULL with a server default, so a NaN must not reach the insert.
        # yfinance reports "no split" as 0.0; the warehouse stores 1.0 (the
        # no-op ratio) so that `split_coefficient > 0` holds and the value can be
        # multiplied straight into an adjustment chain.
        if "dividend_amount" in df.columns:
            df["dividend_amount"] = df["dividend_amount"].fillna(0.0)
        if "split_coefficient" in df.columns:
            df["split_coefficient"] = (
                df["split_coefficient"].fillna(0.0).replace(0.0, 1.0)
            )

        df.index.name = "trade_date"
        # Uppercase: market.daily_bars has CHECK (symbol = upper(symbol)) so that
        # joins to news.article_securities cannot miss on case alone.
        df["symbol"] = self.ticker.strip().upper()
        df["source"] = SOURCE_NAME

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

    def ensure_table(self) -> None:
        """
        Step 2a: Create the market schema and market.daily_bars if missing.

        Both steps are idempotent: CREATE SCHEMA IF NOT EXISTS, then a
        checkfirst create of the DailyBar table only. Other warehouse tables
        are not touched, and an existing daily_bars is never altered — a
        column drift between the model and the live table is not fixed here.
        """
        create_schemas(self.engine)
        DailyBar.__table__.create(self.engine, checkfirst=True)
        _logger.info("Ensured table exists: market.daily_bars")

    def truncate_table(self) -> None:
        """
        Step 2c (optional): Remove all rows from market.daily_bars before loading.

        Use this when you want a clean reload rather than an incremental append.
        The table structure is preserved; only the data is removed.

        Uses DELETE FROM rather than TRUNCATE for cross-backend compatibility
        (SQLite does not support TRUNCATE).
        """
        with self.engine.begin() as conn:
            
            statement = delete(DailyBar)
            conn.execute(statement)
        _logger.info("Truncated market.daily_bars — all existing rows removed")

    def insert(self, df: pd.DataFrame) -> None:
        """
        Step 2d: Write an OHLCV DataFrame to the market.daily_bars table.

        Rows whose ``trade_date`` already exists for this symbol are skipped, so
        the loader is safe to re-run and can be used for incremental top-ups.
        A failed insert is logged and re-raised so the caller can count the
        ticker as failed.

        Uses a SQLAlchemy Core INSERT against the ``DailyBar`` table rather than
        ``DataFrame.to_sql()``. ``to_sql`` takes a bare table *name* and knows
        nothing about the engine's ``schema_translate_map``, so it would look for
        an unqualified ``daily_bars`` and miss ``market.daily_bars`` on Postgres.
        Going through the mapped table also means the column set is checked here
        instead of failing in the database.
        """
        symbol = df["symbol"].iloc[0]

        # Drop rows that already exist in the database to avoid PK conflicts.
        existing = self._existing_dates(symbol)
        before = len(df)
        # Compare date-to-date explicitly. Passing a set of datetime.date to
        # DatetimeIndex.isin() works today but pandas warns it will stop matching
        # in a future version — and a silently-empty skip means every re-run
        # raises a primary key violation instead of being a no-op.
        df = df[[timestamp.date() not in existing for timestamp in df.index]]
        skipped = before - len(df)

        if df.empty:
            _logger.info("[%s] All rows already present — nothing to insert", symbol)
            return

        # Build plain dicts keyed by column name; the DatetimeIndex becomes
        # trade_date as a real date (not a Timestamp) for the DATE column.
        table_columns = {c.name for c in DailyBar.__table__.columns}
        rows: list[dict] = []
        for timestamp, record in df.iterrows():
            row = {
                k: (None if pd.isna(v) else v)
                for k, v in record.items()
                if k in table_columns
            }
            row["trade_date"] = timestamp.date()
            rows.append(row)

        try:
            with self.engine.begin() as conn:
                conn.execute(sa_insert(DailyBar), rows)
        except Exception as exc:
            _logger.error("[%s] Insert failed: %s", symbol, exc)
            raise

        _logger.info(
            "[%s] Inserted %d rows%s",
            symbol,
            len(rows),
            f" (skipped {skipped} existing)" if skipped else "",
        )

    def _existing_dates(self, symbol: str) -> set[date]:
        """Return the set of trade dates already stored for a given symbol."""
        statement = select(DailyBar.trade_date).where(DailyBar.symbol == symbol)

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
    # Tickers are accepted positionally (as the docs and Makefile call it) or
    # via -t/--tickers; both land in args.tickers.
    parser.add_argument(
        "tickers",
        nargs="*",
        help="Ticker symbols (e.g. AAPL MSFT) or a path to a JSON file of tickers",
    )
    parser.add_argument(
        "-t", "--tickers",
        dest="tickers_flag",
        nargs="+",
        metavar="TICKER",
        help="Alternative to the positional form",
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
    args = parser.parse_args()

    args.tickers = args.tickers + (args.tickers_flag or [])
    if not args.tickers:
        parser.error("at least one ticker (or a .json ticker file) is required")
    return args

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
    # Steps 2a–2c: Connect, ensure schema + table exist, prepare table.
    # ----------------------------------------------------------------
    db = StockDatabase(get_engine())
    db.ensure_table()

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
