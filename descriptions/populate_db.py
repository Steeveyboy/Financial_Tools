"""Populate the corporate_db database from descriptions/company_info.json.

This script reads the yfinance data collected by the description_parsing
notebook and upserts Company rows into the database managed by the
``corporate_db`` package.

Usage (from the repo root)::

    python -m descriptions.populate_db                  # default
    python -m descriptions.populate_db --dry-run        # preview without writing
    python -m descriptions.populate_db --file other.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select

# corporate_db imports — the repo root must be on sys.path
from corporate_db.db.connection import get_session
from corporate_db.models.company import Company
from corporate_db.models.exchange import Exchange

logger = logging.getLogger(__name__)

# ── yfinance exchange code → seeded Exchange.code mapping ─────────────────
EXCHANGE_MAP: dict[str, str] = {
    "NYQ": "NYSE",
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    # Add more mappings here as needed (e.g. "TOR": "TSX", "VAN": "TSXV")
}

DEFAULT_FILE = Path(__file__).with_name("company_info.json")


# ── Helpers ───────────────────────────────────────────────────────────────

def load_records(path: Path) -> list[dict[str, Any]]:
    """Load company records from a (possibly concatenated) JSON file.

    The notebook appends to the file in chunks, so the file may contain
    multiple top-level JSON arrays or objects back-to-back.
    """
    content = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    records: list[dict[str, Any]] = []
    idx = 0
    while idx < len(content):
        # skip whitespace between top-level values
        while idx < len(content) and content[idx] in " \t\n\r":
            idx += 1
        if idx >= len(content):
            break
        obj, end_idx = decoder.raw_decode(content, idx)
        if isinstance(obj, list):
            records.extend(obj)
        else:
            records.append(obj)
        idx = end_idx
    return records


def _truncate(value: str | None, max_len: int) -> str | None:
    """Truncate a string to *max_len* characters, or return None."""
    if value is None:
        return None
    return value[:max_len]


def _build_headquarters(rec: dict[str, Any]) -> str | None:
    """Build a 'City, State' string from yfinance fields."""
    parts = [rec.get("city"), rec.get("state")]
    parts = [p for p in parts if p]
    return ", ".join(parts) or None


def record_to_company(
    rec: dict[str, Any],
    exchange_id: int,
) -> Company:
    """Map a single yfinance info dict to a Company ORM instance."""
    return Company(
        name=_truncate(rec.get("longName") or rec.get("shortName", ""), 255),
        ticker=_truncate(rec.get("symbol", ""), 20),
        exchange_id=exchange_id,
        country=_truncate(rec.get("country"), 100),
        sector=_truncate(rec.get("sector"), 100),
        industry=_truncate(rec.get("industry"), 150),
        description=rec.get("longBusinessSummary"),
        website=_truncate(rec.get("website"), 255),
        headquarters=_truncate(_build_headquarters(rec), 255),
        market_cap=rec.get("marketCap"),
        employees=rec.get("fullTimeEmployees"),
        is_active=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────

def populate(path: Path, *, dry_run: bool = False) -> None:
    """Read *path* and upsert companies into the database."""
    records = load_records(path)
    logger.info("Loaded %d records from %s.", len(records), path)

    with get_session() as session:
        # Build a lookup: Exchange.code → Exchange.id
        exchanges: dict[str, int] = {
            row.code: row.id
            for row in session.execute(select(Exchange)).scalars()
        }
        logger.info("Exchange lookup: %s", exchanges)

        # Build a set of existing (ticker, exchange_id) pairs for fast skip
        existing: set[tuple[str, int]] = set(
            session.execute(
                select(Company.ticker, Company.exchange_id)
            ).all()
        )
        logger.info("Existing companies in DB: %d", len(existing))

        inserted = 0
        skipped_exchange = 0
        skipped_dup = 0
        skipped_no_symbol = 0

        for rec in records:
            symbol = rec.get("symbol")
            if not symbol:
                skipped_no_symbol += 1
                continue

            yf_exchange = rec.get("exchange", "")
            exchange_code = EXCHANGE_MAP.get(yf_exchange)
            if exchange_code is None or exchange_code not in exchanges:
                skipped_exchange += 1
                continue

            exchange_id = exchanges[exchange_code]
            key = (symbol, exchange_id)

            if key in existing:
                skipped_dup += 1
                continue

            company = record_to_company(rec, exchange_id)

            if dry_run:
                logger.info("[DRY RUN] Would insert: %s (%s)", company.ticker, company.name)
            else:
                session.add(company)
                existing.add(key)

            inserted += 1

        logger.info(
            "Done — inserted: %d, skipped (no exchange match): %d, "
            "skipped (duplicate): %d, skipped (no symbol): %d.",
            inserted,
            skipped_exchange,
            skipped_dup,
            skipped_no_symbol,
        )

        if dry_run:
            session.rollback()
            print(f"[DRY RUN] Would have inserted {inserted} companies.")
        else:
            # commit is handled by the get_session() context manager
            print(f"Inserted {inserted} companies into the database.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Populate corporate_db from yfinance company_info.json",
    )
    parser.add_argument(
        "--file", "-f",
        type=Path,
        default=DEFAULT_FILE,
        help="Path to company_info.json (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate without writing to the database.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    if not args.file.exists():
        logger.error("File not found: %s", args.file)
        sys.exit(1)

    populate(args.file, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
