# Discovery index

One line per note. Scan this first; open only what's relevant.
See [`README.md`](README.md) for when and how to add one.

| # | Note | Hook |
|---|---|---|
| 001 | [`findata` isn't an installed package: run from the repo root](001-running-python-in-this-repo.md) | Env is conda `finance`; `ModuleNotFoundError: findata` means wrong cwd, not a missing dependency |
| 002 | [Two venvs in-tree; `find .` is unusable](002-search-noise-from-in-tree-venvs.md) | Search with `rg`/Grep or `git ls-files`, never bare `find` |
| 003 | [`docs/schema.sql` is stale](003-schema-truth-source.md) | Columns come from `findata/models/`, not from `schema.sql` |
| 004 | [`insert_articles()` log call is malformed](004-insert-articles-log-call-is-malformed.md) | A "Logging error" traceback after inserts is cosmetic, not a failure |
| 005 | [Postgres schemas + SQLite; `alembic check` lies](005-schemas-and-sqlite.md) | Schemas collapse via `schema_translate_map`; run `alembic check` on Postgres only, and use `sa.func.now()` not `sa.text("now()")` in migrations |
| 006 | [FNSPID must be loaded per file with an all-string schema](006-fnspid-csv-type-inference.md) | `ArrowInvalid: Failed to parse string … as a scalar of type double` means pandas guessed a blank column as float; `dtype=str` does not exist in `datasets` 5.x, and the two CSVs have different headers |
