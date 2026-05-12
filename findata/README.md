# findata

The financial data warehouse package — a single SQLAlchemy 2.0 ORM layer over
one database (PostgreSQL in production, SQLite for local dev) that all ingestion
sources write into.

This package is being built out incrementally; see
[`../docs/CLEANUP_PLAN.md`](../docs/CLEANUP_PLAN.md) for the target structure and
rollout. Today it contains the corporate-profile tables (`exchanges`,
`companies`, `insiders`); news, market-data, and SEC tables are being migrated in.

## Layout

```
findata/
├── __init__.py          # re-exports: Base, Company, Exchange, Insider, get_session, init_db
├── config.py            # DATABASE_URL, ECHO_SQL (reads <repo_root>/.env)
├── __main__.py          # `python -m findata` → init_db()
├── db/
│   ├── base.py          # the single SQLAlchemy DeclarativeBase
│   ├── session.py       # get_engine(), get_session(), init_db()
│   └── migrations/      # the one Alembic tree for every table (env.py, versions/)
└── models/              # one ORM model per table — this is the data model
    ├── exchange.py      # exchanges
    ├── company.py       # companies  (+ Postgres GIN / SQLite FTS5 full-text search)
    └── insider.py       # insiders   (stub)
```

The `alembic.ini` for this tree lives at the **repo root**.

## Usage

```bash
pip install -r findata/requirements.txt
cp .env.example .env          # set DATABASE_URL (postgres or sqlite)

# create tables + seed default exchanges (dev convenience)
python -m findata

# or, the production path — apply migrations
alembic upgrade head
```

```python
from findata import get_session, Company

with get_session() as session:
    session.add(Company(name="Apple Inc.", ticker="AAPL", exchange_id=1))
    # commits on context exit
```

## Migrations

Run `alembic` from the repo root:

```bash
alembic upgrade head                                   # apply pending
alembic downgrade -1                                   # roll back one
alembic revision --autogenerate -m "add new column"    # new migration
```

`env.py` reads `DATABASE_URL` from the environment and imports all models via
`findata.models` so autogenerate can diff against `Base.metadata`.

## Full-text search on `companies`

`companies` carries a searchable `name` + `description`. The DDL is dialect-conditional:

- **PostgreSQL** — GIN index on `to_tsvector('english', name || ' ' || description)`
- **SQLite** — an `company_fts` FTS5 virtual table

Both are created by `init_db()` (event listeners in `models/company.py`) and
mirrored in migration `0001_initial_schema.py`.
