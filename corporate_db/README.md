# corporate_db

A SQLAlchemy-based database layer for aggregating corporate profiles from major
stock exchanges (NYSE, NASDAQ, TSX, TSXV, and others).

This module is **Agent 1** of a multi-phase financial research database project.
It provides the foundational data layer that future agents will extend with data
ingestion adapters, full-text search APIs, a CLI, and more.

---

## What this module does

| Concern | Implementation |
|---------|---------------|
| ORM models | SQLAlchemy 2.0 (`DeclarativeBase`, `Mapped`, `mapped_column`) |
| Schema versioning | Alembic migrations |
| Dev database | SQLite (zero-config, file-based) |
| Prod database | PostgreSQL (set `DATABASE_URL` env var) |
| Full-text search | PostgreSQL: GIN index on `tsvector`; SQLite: FTS5 virtual table |

---

## Directory layout

```
corporate_db/
├── __init__.py              # Re-exports key symbols
├── config.py                # DATABASE_URL, ECHO_SQL settings
├── alembic.ini              # Alembic configuration
├── requirements.txt         # Python dependencies
├── models/
│   ├── base.py              # Shared DeclarativeBase
│   ├── exchange.py          # Exchange model
│   ├── company.py           # Company model (with FTS support)
│   └── insider.py           # Insider stub model (Agent 7)
└── db/
    ├── connection.py        # get_engine(), get_session(), init_db()
    ├── schema.sql           # PostgreSQL DDL reference
    └── migrations/
        ├── env.py           # Alembic env — imports all models
        ├── script.py.mako   # Migration file template
        └── versions/
            └── 0001_initial_schema.py
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r corporate_db/requirements.txt
```

> **SQLite users**: `psycopg2-binary` is only required for PostgreSQL.
> You can safely omit it: `pip install sqlalchemy alembic python-dotenv`

### 2. (Optional) Create a `.env` file

```ini
# .env  — place in the repo root or set these variables in your shell
DATABASE_URL=sqlite:///corporate_db.sqlite3   # default
# DATABASE_URL=postgresql+psycopg2://user:pass@localhost/corp_db
ECHO_SQL=0   # set to 1 for verbose SQL logging
```

---

## SQLite (development)

Initialize the database (creates tables + seeds default exchanges):

```bash
python -m corporate_db.db.connection
```

Or from Python:

```python
from corporate_db.db.connection import init_db
init_db()
```

---

## PostgreSQL (production)

1. Set the environment variable:
   ```bash
   export DATABASE_URL="postgresql+psycopg2://user:pass@localhost/corp_db"
   ```
2. Run the Alembic migration:
   ```bash
   cd corporate_db
   alembic upgrade head
   ```

---

## Running Alembic migrations

```bash
# From the corporate_db/ directory:
alembic upgrade head          # apply all pending migrations
alembic downgrade -1          # roll back the last migration
alembic revision --autogenerate -m "add new column"   # generate a new migration

# Or from the repo root (using the -c flag):
alembic -c corporate_db/alembic.ini upgrade head
```

---

## Model overview

### `Exchange`

Reference data for a stock exchange.  Seeded with NYSE, NASDAQ, TSX, and TSXV
by `init_db()`.  Add new exchanges by inserting rows into this table — no
schema change required.

```python
from corporate_db.models.exchange import Exchange

exchange = Exchange(
    code="LSE",
    name="London Stock Exchange",
    country="United Kingdom",
    currency="GBP",
    timezone="Europe/London",
)
```

### `Company`

Corporate profile for a company listed on an exchange.

```python
from corporate_db.models.company import Company

company = Company(
    name="Apple Inc.",
    ticker="AAPL",
    exchange_id=1,   # NYSE exchange id
    sector="Information Technology",
    industry="Technology Hardware, Storage & Peripherals",
    description="Apple designs, manufactures and markets smartphones...",
    cik="0000320193",
    is_active=True,
)
```

### `Insider` *(stub — Agent 7)*

Represents a board member or reporting insider associated with a company.  The
model is intentionally minimal and will be extended in a future agent.

---

## Querying examples

```python
from corporate_db.db.connection import get_session
from corporate_db.models.company import Company

# List all active companies in the Technology sector
with get_session() as session:
    companies = (
        session.query(Company)
        .filter_by(sector="Information Technology", is_active=True)
        .all()
    )

# Full-text search (PostgreSQL)
with get_session() as session:
    results = session.execute(
        """
        SELECT id, name, ticker
        FROM   companies
        WHERE  to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,''))
               @@ plainto_tsquery('english', :query)
        """,
        {"query": "semiconductor chips"},
    ).fetchall()

# Full-text search (SQLite — FTS5)
with get_session() as session:
    results = session.execute(
        "SELECT id, name FROM company_fts WHERE company_fts MATCH :q",
        {"q": "semiconductor chips"},
    ).fetchall()
```

---

## Future extensibility

- **New exchanges**: Insert a row into `exchanges` — no migration needed.
- **New company fields**: Add a column to `Company` and run `alembic revision --autogenerate`.
- **Insider detail (Agent 7)**: Extend `Insider` with compensation, share-ownership, and transaction history columns.
- **Data ingestion (Agent 2+)**: Implement adapters that populate `Company` rows from external APIs (SEC EDGAR, SEDAR+, Yahoo Finance, etc.).
- **CLI (future agent)**: Build a Typer/Click CLI over `get_session()` for interactive queries.
