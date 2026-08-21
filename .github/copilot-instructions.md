# Copilot Instructions

This repository keeps **one** copy of each fact. This file deliberately does not
restate the architecture; it points at the files that own it. Open them.

## Read these, in this order

1. [`../docs/REPO_MAP.md`](../docs/REPO_MAP.md) — where everything lives, entry
   points, **paths that no longer exist**, search hygiene, invariants.
2. [`../CLAUDE.md`](../CLAUDE.md) — rules of engagement and current priorities.
3. [`../docs/RECIPES.md`](../docs/RECIPES.md) — how to add an extractor,
   transformer, table/column, or test.
4. [`../docs/discoveries/INDEX.md`](../docs/discoveries/INDEX.md) — non-obvious
   things previous agents learned; add to it when you learn one.

## The 30-second version

- One Python package: `findata/`. One `DeclarativeBase` (`findata/db/base.py`),
  one model per table under `findata/models/`, one Alembic tree
  (`findata/db/migrations/`) driven by `alembic.ini` at the repo root.
- News ETL is the active focus and runs in two independent phases —
  extract to `articles`, then transform stored rows — so transforms can be
  re-run retroactively without re-fetching.
- `findata/sources/news/db/repository.py::ArticleRepository` is the sole SQL
  boundary for news. No raw SQL anywhere else.
- Run everything from the repo root. Tests: `python -m pytest`.
- `SentimentAnalysis/` is legacy and out of scope.

## Work tracking

Issues carry an **Agent Instructions** section (see `ISSUE_TEMPLATE/`) with exact
files, interface contracts, and acceptance criteria. Labels route work:
`agent:coding`, `agent:testing`, `agent:docs`.

Open implementation stubs are tracked in GitHub Issues and `REPO_REVIEW.md` —
not in this file, which cannot be kept current.
