# 003 — `docs/schema.sql` is stale; the models are the schema

- **Verified against:** commit `b675cfb` on 2026-08-21
- **Applies to:** `docs/schema.sql`, `findata/models/`, `findata/db/migrations/`

## What I found

`docs/schema.sql` is a hand-written snapshot containing only `exchanges`,
`companies`, `insiders`, `articles`, `article_tickers`. It predates
`daily_ohlcv` (migration `0003`) and the sentiment work, and nothing regenerates it.

The authoritative schema is `Base.metadata`, i.e. the model files under
`findata/models/` plus the Alembic tree under `findata/db/migrations/versions/`.

## Why it bites

Answering "what columns does `articles` have?" from `schema.sql` gives an answer
that is confidently wrong — it omits later columns entirely.

## What to do

- Read `findata/models/<table>.py` for columns, and the highest-numbered
  migration for what has actually been applied.
- Treat `schema.sql` as documentation-of-record only, and update or delete it
  rather than trusting it.
