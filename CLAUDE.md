# CLAUDE.md

Guidance for Claude Code working in this repository. This file is loaded into
every session, so it stays short: it is a **router**, not a manual. Details live
in the documents it points to — read those on demand rather than assuming.

## Repository Overview

A Python repo being consolidated into a single Postgres-backed financial data
warehouse ("Resonance Desk"). The end goal is one package (`findata/`) with one
ORM `Base`, one Alembic history, and one set of ingestion sources. This repo is
the **backend engine**; the demo frontend is a separate repo,
[Resonance-Desk](https://github.com/Steeveyboy/resonance-desk) (Streamlit + LLM agents).

The repo is mid-migration. The active development focus is the news source under
`findata/sources/news/`.

## Start here

| Before you… | Read |
|---|---|
| touch anything | [`docs/REPO_MAP.md`](docs/REPO_MAP.md) — paths, entry points, dead paths, invariants |
| add an extractor / transformer / table / test | [`docs/RECIPES.md`](docs/RECIPES.md) |
| debug something odd | [`docs/discoveries/INDEX.md`](docs/discoveries/INDEX.md) — what previous agents learned the hard way |
| pick work | "Current Priorities" below, then [`REPO_REVIEW.md`](REPO_REVIEW.md) |
| change the repo's shape | [`docs/CLEANUP_PLAN.md`](docs/CLEANUP_PLAN.md) |
| work on news internals | [`findata/sources/news/README.md`](findata/sources/news/README.md) |
| work on sentiment | [`docs/SENTIMENT_TRANSFORM.md`](docs/SENTIMENT_TRANSFORM.md) |

`docs/REPO_MAP.md` is the navigation source of truth. If another document
disagrees with it about a path, REPO_MAP wins — and fix the other document.

## How to be a good agent

- **Don't run commands that need the user's input.** No interactive prompts, no
  `alembic upgrade` against the user's live Postgres, no long-running servers.
  Write the code, then hand the user the exact command to run and review.
- **The user is particular.** Prefer producing reviewable output over acting.
- **Verify what you can, cheaply.** `python -m pytest` from the repo root runs
  against in-memory SQLite and touches nothing real — run it before reporting done.
  If you can't run something, say so and give the command.
- **Read the `.md` files scattered around the repo** before inferring from code.
- **Write down what you discover.** Non-obvious findings go in
  [`docs/discoveries/`](docs/discoveries/README.md) as a numbered note plus an
  `INDEX.md` line. Navigation facts go in `REPO_MAP.md`; procedures go in
  `RECIPES.md`. One fact, one home — never paste a copy into a second file.
- **Fix drift when you hit it.** A wrong path in a doc costs the next agent more
  than it costs you to correct it.

## Current Priorities (set 2026-08, overrides REPO_REVIEW.md sequencing)

The repo is a portfolio piece first. Work in this order:

1. **Make something run / show** — README positioning (engine role, architecture
   diagram, "what this demonstrates") and visible proof the pipelines run.
2. **The interesting half** — sentiment transform end-to-end (REPO_REVIEW #6):
   migration `0004` (`sentiment_score`, `transform_log`), FinBERT scoring, the
   `_persist()` branch, `transform_news.py`. Then the sentiment overlay in the demo.
3. **Tests + honest CI** (REPO_REVIEW #1): no `|| echo` escape in CI, pytest
   against in-memory SQLite.

Small P0 bug fixes (REPO_REVIEW #3–#5) can ride along with whichever item touches
their code.

## Non-negotiables

- **One `Base`, one Alembic tree.** New table → model under `findata/models/`,
  imported in `findata/models/__init__.py`, plus a migration.
- **No raw SQL outside a repository class** (`ArticleRepository` for news).
- **`logging` with a module-level `_logger`, never `print()`.**
- **Sentiment is local FinBERT** — no Claude/OpenAI API calls in this backend repo.
- **`SentimentAnalysis/` is off limits.** Legacy Flask app, unrelated to the
  warehouse, kept only until Phase 5 moves it to `legacy/`.
- **Don't run migrations or DDL against the user's Postgres.** Verify against
  SQLite; leave the real command to the user.

## Environment

| Variable | Used by | Notes |
|---|---|---|
| `DATABASE_URL` | all of `findata` | SQLAlchemy URL; required |
| `NEWS_LOG_LEVEL` | `findata.sources.news` | Default: `INFO` |
| `ECHO_SQL` | `findata` | Truthy → log all SQL |
| `START_DATE`, `END_DATE` | `findata.sources.market` | Optional `YYYY-MM-DD` OHLCV defaults |

`.env` at the repo root; every module calls `load_dotenv()`. See `.env.example`.

## SEC EDGAR (Phase 6, when SEC ingestion returns)

Required header on every request:

```python
{"user-agent": "www.jonsteeves.dev jonathonsteeves@cmail.carleton.ca"}
```
