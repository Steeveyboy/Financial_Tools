# Company Descriptions

Programmatic pipeline for fetching company profiles (descriptions, metadata, officers) from public APIs and loading them into a PostgreSQL data warehouse.

## Architecture

```
descriptions/
├── application.yaml          # Configurable settings (table names, sources, filters)
├── config.py                 # YAML + environment variable config loader
├── fetcher.py                # Ticker list retrieval & yfinance company info fetcher
├── main.py                   # CLI entry point
├── db/
│   ├── postgres.py           # Reusable PostgreSQL client (SQLAlchemy)
│   └── models.py             # Declarative table models (companies, company_officers)
├── requirements.txt
└── (notebooks)               # Original exploratory notebooks
```

### Data Flow

1. **Ticker list** — Fetches NYSE + NASDAQ ticker JSONs from [US-Stock-Symbols](https://github.com/rreichel3/US-Stock-Symbols)
2. **Filtering** — Removes invalid symbols, applies market-cap and country filters (configurable in `application.yaml`)
3. **Company info** — Uses `yfinance` to pull detailed profiles for each ticker
4. **PostgreSQL load** — Upserts company rows and replaces officer rows via SQLAlchemy

### Database Tables

| Table | Description |
|-------|-------------|
| `companies` | Core profile: symbol, name, description, sector, industry, location, financials snapshot |
| `company_officers` | Executives linked to `companies.symbol` via foreign key |

## Notebooks

| Notebook | Description |
|----------|-------------|
| `description_parsing.ipynb` | Original exploratory notebook for parsing company data |
| `nyse_description_search.ipynb` | Interactive search/filter tool for NYSE descriptions |

## Setup

```bash
cd descriptions
pip install -r requirements.txt
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `POSTGRES_CONNECTION_STRING` | PostgreSQL URI, e.g. `postgresql://user:pass@localhost:5432/financial_datawarehouse` |
| `DATABASE_URL` | Alternative name (checked if the above is not set) |

## Usage

```bash
# From the repo root:

# Fetch all tickers and load into Postgres
python -m descriptions

# Fetch only specific symbols
python -m descriptions --symbols AAPL MSFT GOOGL

# Limit to first 20 tickers (useful for testing)
python -m descriptions --limit 20

# Dry-run — fetch data, print summary, skip DB writes
python -m descriptions --dry-run --limit 5

# Debug SQL output
python -m descriptions --echo-sql --symbols TSLA
```

## Configuration

Edit `application.yaml` to adjust:

- **`database.schema`** – Postgres schema (default `public`)
- **`database.tables`** – Table name mapping
- **`fetcher.sources`** – Ticker list URLs
- **`fetcher.min_market_cap`** – Minimum market cap filter
- **`fetcher.accepted_countries`** – Country allow-list
- **`fetcher.rate_limit_delay`** – Seconds between yfinance API calls

## Reusable Postgres Component

`db/postgres.py` provides a generic `PostgresClient` that can be imported by other modules in this data warehouse:

```python
from descriptions.db.postgres import PostgresClient

with PostgresClient(connection_string="postgresql://...") as db:
    db.create_tables()
    db.upsert(MyModel, records, conflict_column="id")
    count = db.count(MyModel)
```

## Tech Stack

- **Data:** Pandas, yfinance
- **Database:** SQLAlchemy, psycopg2, PostgreSQL
- **Config:** PyYAML, environment variables
