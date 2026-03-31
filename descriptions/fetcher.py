"""Fetch company descriptions and metadata from public APIs.

Data flow:
1. Fetch ticker lists from GitHub (NYSE + NASDAQ full ticker JSONs)
2. Filter by market cap, country, and symbol validity
3. Use yfinance to pull detailed company info for each symbol
4. Return structured dicts ready for database insertion
"""

from __future__ import annotations

import logging
import time
from typing import Any

import pandas as pd
import requests
import yfinance as yf

from descriptions import config

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Step 1 — Ticker list retrieval & filtering
# ------------------------------------------------------------------

def fetch_ticker_list() -> pd.DataFrame:
    """Download NYSE + NASDAQ ticker lists and return a filtered DataFrame.

    Filters applied (mirroring the original notebook logic):
    - Remove symbols containing ``^``
    - Coerce market cap to numeric; drop rows without valid market cap
    - Replace ``/`` with ``-`` in symbols (e.g. ``BRK/B`` → ``BRK-B``)
    - Minimum market cap threshold from config
    - Country allow-list from config
    """
    sources: dict[str, str] = config.get("fetcher.sources", {})
    if not sources:
        raise RuntimeError("No ticker sources defined in application.yaml")

    frames: list[pd.DataFrame] = []
    for name, url in sources.items():
        logger.info("Fetching ticker list: %s → %s", name, url)
        try:
            df = pd.read_json(url)
            logger.info("  Loaded %d tickers from %s", len(df), name)
            frames.append(df)
        except Exception as e:
            logger.warning("  Failed to load %s: %s", name, e)

    if not frames:
        raise RuntimeError("Could not load any ticker source")

    df_raw = pd.concat(frames, ignore_index=True)

    # Symbol cleanup
    df_raw = df_raw[~df_raw["symbol"].str.contains(r"\^", na=False)]
    df_raw["symbol"] = df_raw["symbol"].str.replace("/", "-", regex=False)

    # Market cap filter
    df_raw["marketCap"] = pd.to_numeric(df_raw["marketCap"], errors="coerce")
    df_raw.dropna(subset=["marketCap"], inplace=True)
    min_cap = config.get("fetcher.min_market_cap", 10_000_000)
    df_raw = df_raw[df_raw["marketCap"] > min_cap]

    # Country filter
    accepted = set(config.get("fetcher.accepted_countries", []))
    if accepted:
        df_raw = df_raw[df_raw["country"].isin(accepted)]

    # Keep only useful columns that exist
    keep = ["symbol", "name", "marketCap", "country", "ipoyear", "industry", "sector"]
    keep = [c for c in keep if c in df_raw.columns]
    df = df_raw[keep].copy()
    df.reset_index(drop=True, inplace=True)
    logger.info("Filtered ticker list: %d symbols", len(df))
    return df


# ------------------------------------------------------------------
# Step 2 — Fetch detailed company info via yfinance
# ------------------------------------------------------------------

def _map_yf_info(info: dict[str, Any]) -> dict[str, Any]:
    """Map a yfinance ``info`` dict to our database column schema."""
    return {
        "symbol": info.get("symbol"),
        "short_name": info.get("shortName"),
        "long_name": info.get("longName"),
        "business_summary": info.get("longBusinessSummary"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "city": info.get("city"),
        "state": info.get("state"),
        "zip_code": info.get("zip"),
        "address": info.get("address1"),
        "phone": info.get("phone"),
        "website": info.get("website"),
        "full_time_employees": info.get("fullTimeEmployees"),
        "market_cap": info.get("marketCap"),
        "exchange": info.get("exchange"),
        "currency": info.get("currency"),
        "quote_type": info.get("quoteType"),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "revenue": info.get("totalRevenue"),
        "ebitda": info.get("ebitda"),
        "net_income": info.get("netIncomeToCommon"),
        "profit_margin": info.get("profitMargins"),
    }


def _map_officers(symbol: str, info: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract company officer records from yfinance info."""
    officers: list[dict[str, Any]] = []
    for off in info.get("companyOfficers", []):
        officers.append(
            {
                "company_symbol": symbol,
                "name": off.get("name"),
                "title": off.get("title"),
                "age": off.get("age"),
                "year_born": off.get("yearBorn"),
                "fiscal_year": off.get("fiscalYear"),
                "total_pay": off.get("totalPay"),
                "exercised_value": off.get("exercisedValue"),
                "unexercised_value": off.get("unexercisedValue"),
            }
        )
    return officers


def fetch_company_details(
    symbols: list[str],
    rate_limit: float | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch detailed company info for each *symbol* via yfinance.

    Parameters
    ----------
    symbols : list[str]
        Ticker symbols to fetch.
    rate_limit : float | None
        Seconds to sleep between requests.  Falls back to config value.

    Returns
    -------
    tuple of (company_records, officer_records)
        Each is a list of dicts ready for DB insertion.
    """
    if rate_limit is None:
        rate_limit = config.get("fetcher.rate_limit_delay", 0.2)

    company_records: list[dict[str, Any]] = []
    officer_records: list[dict[str, Any]] = []
    total = len(symbols)

    for idx, symbol in enumerate(symbols, 1):
        logger.info("[%d/%d] Fetching %s …", idx, total, symbol)
        try:
            ticker = yf.Ticker(symbol)
            info: dict[str, Any] = ticker.info

            if not info or not info.get("symbol"):
                logger.warning("  No data returned for %s", symbol)
                continue

            company_records.append(_map_yf_info(info))
            officer_records.extend(_map_officers(info["symbol"], info))

        except Exception as e:
            logger.error("  Error fetching %s: %s", symbol, e)

        if rate_limit > 0:
            time.sleep(rate_limit)

    logger.info(
        "Fetched %d companies, %d officers",
        len(company_records),
        len(officer_records),
    )
    return company_records, officer_records
