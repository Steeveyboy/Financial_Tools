# 005 — Postgres schemas + SQLite: the translate map, and why `alembic check` lies

**Date:** 2026-09-25
**Context:** the `resonance_desk` rebuild moved every table into a Postgres
schema (`reference` / `market` / `news`) while the test suite still runs on
in-memory SQLite.

## SQLite has no schemas, so they are collapsed at the engine

Every model declares `schema=`. SQLite would be asked for `news.articles` and
fail. `findata/db/base.py` provides the fix:

```python
schema_translate_map_for("sqlite")      # {'reference': None, 'market': None, 'news': None}
schema_translate_map_for("postgresql")  # {}
```

Applied as a connection execution option, which **returns a new engine** — the
result must be used, not discarded:

```python
engine = engine.execution_options(schema_translate_map=schema_translate_map_for(engine.dialect.name))
```

Three places apply it, and a fourth needs to if you add one:

| Place | Why |
|---|---|
| `findata.db.session.get_engine()` | the default engine |
| `ArticleRepository.__init__` | an engine *injected* by a caller or test carries no map |
| `findata/db/migrations/env.py` | `alembic upgrade` on SQLite |
| `tests/conftest.py` fixtures | engines handed to code other than the repository |

**This only works because no table name repeats across schemas.** Collapsing is
lossless today; two tables sharing a name in different schemas would silently
collide on SQLite. That is a constraint on future table names.

## `alembic check` is meaningless on SQLite here

The translate map governs **SQL execution, not metadata comparison**.
Autogenerate diffs `Base.metadata` (where a table's schema is `'news'`) against
SQLite reflection (where it is `None`), concludes the two are different objects,
and reports *every table as both added and removed*:

```
Detected removed table 'article_securities'
Detected added index 'ix_insiders_company_id' ...
```

That output is noise. **Run `alembic check` against Postgres only.**

For SQLite, `tests/findata/db/test_migration_matches_models.py` does the
equivalent job: build one database with `alembic upgrade head`, another with
`Base.metadata.create_all()`, compare object sets and per-table clause sets.
Clause sets must be compared **order-independently** — both paths emit identical
columns and constraints in different orders.

## Two bugs that comparison caught

**1. `sa.text("now()")` in a migration breaks SQLite.** `sa.text()` is emitted
verbatim, so SQLite got `DEFAULT (now())` — a function it does not have — and
every INSERT would have failed. DDL succeeded; only writes broke, so a schema
diff alone would not have found it. Use `sa.func.now()`, which compiles to
`now()` on Postgres and `CURRENT_TIMESTAMP` on SQLite.

**2. SQLite does not round-trip timezone awareness.** Postgres `timestamptz`
returns an aware datetime; SQLite returns the same row naive. Code comparing a
value read on Postgres against one read on SQLite raises `TypeError`.
`findata.db.types.UTCDateTime` is a `TypeDecorator` that normalizes on write and
re-stamps UTC on read, so both backends behave identically. Its `impl` is
`DateTime(timezone=True)`, so DDL and autogenerate are unaffected.

Note this makes `column.type.python_type` raise `NotImplementedError` — anything
introspecting column types must handle that (see `_python_type()` in
`tests/findata/models/test_naming_convention.py`), and the `timezone` flag lives
on `column.type.impl`, not `column.type`.

## FTS5 shadow tables

SQLite builds `companies_fts_data`, `_idx`, `_docsize`, `_config` behind the FTS5
virtual table. Autogenerate sees them as unknown tables and proposes dropping
them. `env.py` filters them by prefix (`_FTS_SHADOW_PREFIXES`) alongside the
named exclusions in `_EVENT_CREATED_OBJECTS`. Adding event-listener DDL means
adding it there too.
