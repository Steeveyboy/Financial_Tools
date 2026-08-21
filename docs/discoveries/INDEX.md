# Discovery index

One line per note. Scan this first; open only what's relevant.
See [`README.md`](README.md) for when and how to add one.

| # | Note | Hook |
|---|---|---|
| 001 | [Nothing is installed: run from the repo root](001-running-python-in-this-repo.md) | `ModuleNotFoundError: findata` means wrong cwd, not a missing dependency |
| 002 | [Two venvs in-tree; `find .` is unusable](002-search-noise-from-in-tree-venvs.md) | Search with `rg`/Grep or `git ls-files`, never bare `find` |
| 003 | [`docs/schema.sql` is stale](003-schema-truth-source.md) | Columns come from `findata/models/`, not from `schema.sql` |
| 004 | [`insert_articles()` log call is malformed](004-insert-articles-log-call-is-malformed.md) | A "Logging error" traceback after inserts is cosmetic, not a failure |
