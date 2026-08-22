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

## How to be a good agent

Avoid running commands that require the users input.
The user is particular, so focus on writing the code, then provide commands that the user can run, to test the changes by visually reviewing the outputs.
Refer to the .md files scattered around the repo.
Write down discoveries you make about the repo in .md files in the docs folder.

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

Entry points at the repo root: `load_news_articles.py` (news ETL), `Makefile` (common targets).

## findata.sources.news — News ETL Architecture

The pipeline has two independent phases so transforms can be re-run retroactively without re-fetching:

```
Phase 1 — Extraction:  Extractor(s) → ArticleRepository.insert_articles() → articles / article_tickers tables
Phase 2 — Transform:   articles table → Transformer(s) → sentiment_score column / article_tickers table
```

**Key design points:**
- The `articles` / `article_tickers` tables are ORM models in `findata.models` (`Article`, `ArticleTicker`). `findata/sources/news/db/repository.py` (`ArticleRepository`) drives them through SQLAlchemy 2.0 sessions.
- `ArticleRepository()` falls back to `findata.db.session.get_engine()` when no engine is passed in (so callers can just write `ArticleRepository()` against the configured `DATABASE_URL`).
- `ArticleExtractor` subclasses define `source_id` and `extract() -> list[dict]`. URL is the deduplication key.
- If an extractor dict includes `mentioned_tickers`, the pipeline links them at load time (no EntityTransformer needed).
- `article_tickers` has a composite primary key `(article_id, ticker)`. Inserts use dialect-aware `INSERT … ON CONFLICT DO NOTHING` (Postgres + SQLite) so transforms can be re-run safely.
- `ArticleRepository` is the sole SQL layer — never write raw SQL outside it.
- `get_untransformed()` is a stub that currently returns all articles; a `transform_log` table is the planned fix.
- `TransformationPipeline._persist()` has a TODO branch for each `transform_id` — add persistence logic there when implementing a new transformer.

**Setup:**
```bash
pip install -r findata/sources/news/requirements.txt
export DATABASE_URL="sqlite:///resonance.db"   # or postgresql://...
```

Run the pipeline from the project root (`Financial_Tools/`): `python load_news_articles.py`.

## findata — warehouse package

The target home for the whole warehouse (see `docs/CLEANUP_PLAN.md`). Structure:
- `findata/db/base.py` — the one `DeclarativeBase`. Every table is an ORM model under `findata/models/` inheriting it, so `Base.metadata` is the authoritative table list.
- `findata/db/session.py` — `get_engine()`, `get_session()` (commit/rollback context manager), `init_db()` (create_all + seed default exchanges).
- `findata/db/migrations/` — the single Alembic tree; `alembic.ini` is at the repo root. `env.py` reads `DATABASE_URL` and imports `findata.models` for autogenerate.
- `findata/config.py` — `DATABASE_URL` / `ECHO_SQL`, loads `<repo_root>/.env`.
- `findata/sources/` — extract/transform packages for each upstream source. Currently `findata/sources/news/` (RSS + FNSPID); `market/`, `corporate/`, `sec/` arrive in later phases.

`python -m findata` runs `init_db()` (dev convenience); `alembic upgrade head` is the production path. Currently holds the corporate tables (`exchanges`, `companies`, `insiders`) and the news tables (`articles`, `article_tickers`); market / SEC tables migrate in per the cleanup plan. `companies` has dialect-conditional full-text search (Postgres GIN / SQLite FTS5) — see `models/company.py`.

## SentimentAnalysis

You won't be working with SentimentAnalysis/ section of the repo it is a legacy project that remains in the repo.


## SEC / XBRL (Phase 6)

`FinancialWebScrapers/` has been removed from the working tree (commit `e8e90a8`). Phase 6 of the cleanup plan re-introduces SEC ingestion under `findata/sources/sec/`, writing directly to Postgres (no MongoDB). The XBRL tag mappings and SEC EDGAR scripts will need to be recovered from git history when that phase begins.

**SEC EDGAR API — required header (for future use):**
```python
{"user-agent": "www.jonsteeves.dev jonathonsteeves@cmail.carleton.ca"}
```

## Environment Variables

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
