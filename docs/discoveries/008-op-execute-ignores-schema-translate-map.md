# 008 — `op.execute()` in a migration ignores the SQLite schema collapse

- **Verified against:** commit `a5dd024` on 2026-10-13
- **Applies to:** `findata/db/migrations/versions/`, any migration that runs a
  data statement (`DELETE` / `UPDATE` / `INSERT`) rather than DDL

## What I found

`env.py` puts a `schema_translate_map` on the connection so `schema="news"`
renders unqualified on SQLite. `op.create_table`, `op.create_index` and friends
honour it. A SQLAlchemy Core statement passed to `op.execute()` does not:

```python
staged = sa.table("dojo_stock_news", sa.column("id"), schema=SCHEMA_NEWS)
op.execute(sa.delete(staged))   # SQLite: no such table: news.dojo_stock_news
```

## Why it bites

The migration works on Postgres and fails only on SQLite, which is what
`tests/findata/db/test_migration_matches_models.py` runs — all four of its tests
error at fixture setup with `no such table: news.<table>`.

## What to do

Choose the schema yourself when building a table for `op.execute()`, as
`0003_dojo_stock_news_unique.py` does:

```python
schema=None if op.get_bind().dialect.name == "sqlite" else SCHEMA_NEWS
```
