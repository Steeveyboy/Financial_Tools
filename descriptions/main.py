"""Entry point — fetch company descriptions and load into PostgreSQL.

Usage:
    # Fetch all tickers from configured sources and load into Postgres
    python -m descriptions.main

    # Fetch only specific symbols
    python -m descriptions.main --symbols AAPL MSFT GOOGL

    # Dry-run: fetch data but don't write to DB (print summary instead)
    python -m descriptions.main --dry-run

    # Limit how many tickers to process (useful for testing)
    python -m descriptions.main --limit 20

Environment variables required:
    POSTGRES_CONNECTION_STRING  (or DATABASE_URL)
        e.g. postgresql://user:pass@localhost:5432/financial_datawarehouse
"""

from __future__ import annotations

import argparse
import logging
import sys

from descriptions import config
from descriptions.db.models import Company, CompanyOfficer
from descriptions.db.postgres import PostgresClient
from descriptions.fetcher import fetch_company_details, fetch_ticker_list

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch company descriptions and load them into PostgreSQL.",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Only fetch these specific ticker symbols.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max number of tickers to process (0 = unlimited).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data but skip database writes.",
    )
    parser.add_argument(
        "--echo-sql",
        action="store_true",
        help="Log all SQL statements (debug).",
    )
    return parser


def run(args: argparse.Namespace) -> None:
    # ── Resolve symbols ──────────────────────────────────────────────
    if args.symbols:
        symbols = [s.upper() for s in args.symbols]
        logger.info("Using %d user-specified symbols.", len(symbols))
    else:
        logger.info("Fetching ticker lists from configured sources …")
        df = fetch_ticker_list()
        symbols = df["symbol"].tolist()

    if args.limit > 0:
        symbols = symbols[: args.limit]
        logger.info("Limited to first %d symbols.", args.limit)

    logger.info("Will fetch data for %d symbols.", len(symbols))

    # ── Fetch via yfinance ───────────────────────────────────────────
    company_records, officer_records = fetch_company_details(symbols)

    if not company_records:
        logger.warning("No company records were fetched — nothing to do.")
        return

    logger.info(
        "Fetched %d companies, %d officers.",
        len(company_records),
        len(officer_records),
    )

    # ── Dry-run guard ────────────────────────────────────────────────
    if args.dry_run:
        logger.info("Dry-run mode — skipping database writes.")
        for rec in company_records[:5]:
            logger.info("  %s — %s", rec["symbol"], rec["short_name"])
        if len(company_records) > 5:
            logger.info("  … and %d more.", len(company_records) - 5)
        return

    # ── Database writes ──────────────────────────────────────────────
    conn_str = config.get_connection_string()
    schema = config.get("database.schema", "public")

    with PostgresClient(conn_str, schema=schema, echo=args.echo_sql) as db:
        db.create_tables()

        n_companies = db.upsert(
            Company,
            company_records,
            conflict_column="symbol",
        )
        logger.info("Upserted %d company rows.", n_companies)

        if officer_records:
            # Clear existing officers for the symbols we just fetched,
            # then re-insert so we don't accumulate stale rows.
            fetched_symbols = [r["symbol"] for r in company_records if r.get("symbol")]
            with db.session() as sess:
                sess.query(CompanyOfficer).filter(
                    CompanyOfficer.company_symbol.in_(fetched_symbols)
                ).delete(synchronize_session=False)

            n_officers = db.bulk_insert(CompanyOfficer, officer_records)
            logger.info("Inserted %d officer rows.", n_officers)

    logger.info("Done.")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        run(args)
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
