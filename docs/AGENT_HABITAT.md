# Agent habitat — analysis and changes

An assessment of how well this repo supports agents working in it, and what was
changed on 2026-08-21 to improve it. Written against commit `b675cfb`.

## The two questions

**How can agents navigate this repo better?** By having exactly one document that
owns "where things are", and by that document naming the *dead* paths as
explicitly as the live ones. This repo's history is a series of renames
(`news_articles/` → `findata/sources/news/`, `corporate_db/` → `findata/db/`,
`market_data/` → `findata/sources/market/`), and the old names survive in
docstrings, workflows, and instruction files. An agent grepping a dead path gets
zero hits and has no way to tell "doesn't exist" from "I searched wrong".

**Where can agents persist discoveries?** In `docs/discoveries/` — numbered
notes plus an index, with an explicit contract for what belongs there. Before,
`CLAUDE.md` said "write down discoveries in the docs folder" with no format, no
index, and no distinction between a discovery and a progress report, so nothing
was ever written.

## Findings

### 1. Instruction sprawl with drift (worst problem)

The same architecture description existed in four places — `CLAUDE.md`,
`.github/copilot-instructions.md`, `.github/agents/coding-agent.md`,
`.github/agents/testing-agent.md` — roughly 400 lines of overlap, and they had
already drifted apart. `CLAUDE.md` and `copilot-instructions.md` both listed
`market_data/` as a top-level module; that directory has not existed since
Phase 3. `copilot-instructions.md` carried a stub table listing work that has
since been done.

Duplication guarantees drift, and a confidently wrong instruction file is worse
than no instruction file: the agent doesn't verify what it has just been told.

### 2. CLAUDE.md was a manual, not a router

It is loaded into every session, so every line competes for attention with the
actual task. Half of it restated things the code says better.

### 3. No verification loop

There was no `tests/` directory at all, yet CI, `CLAUDE.md`, and both agent
instruction files told agents to run `python -m pytest tests/`. CI hid the
absence behind `|| echo "No tests found yet"`, so the pipeline was green by
construction. An agent that cannot cheaply check its own work has to either
guess or ask the user to run things — and this user explicitly prefers not to be
handed commands to babysit.

### 4. Invocation was guesswork

No `pyproject.toml`, no install step, four separate `requirements.txt` files, and
imports that only resolve from the repo root. The existing
`.claude/settings.local.json` shows the workaround an agent converged on:
`PYTHONPATH=. .venv/bin/python …`.

### 5. Search noise

`./.venv/` and `./SentimentAnalysis/.venv/` sit in the working tree. Any unscoped
`find`/`ls -R` returns tens of thousands of site-packages files.

### 6. A stale schema file that reads as authoritative

`docs/schema.sql` looks like the schema of record but predates `daily_ohlcv` and
the sentiment columns.

## What changed

| Change | Why |
|---|---|
| **`docs/REPO_MAP.md`** (new) | One navigation source of truth: tree, entry points, doc routing table, **false-trails table** of renamed paths, search hygiene, invariants. |
| **`docs/RECIPES.md`** (new) | The single copy of "how to add an extractor / transformer / table / test". |
| **`docs/discoveries/`** (new) | Field notebook: `README.md` (the contract for what belongs there), `_TEMPLATE.md`, `INDEX.md`, and four seeded notes from this analysis. |
| **`CLAUDE.md`** rewritten | Now a ~90-line router: overview, "start here" table, rules of engagement, priorities, non-negotiables. Architecture detail moved to the files that own it. |
| **`.github/copilot-instructions.md`** rewritten | Pointer file + 30-second orientation instead of a drifting second copy. |
| **`.github/agents/*.md`** rewritten | Point at `RECIPES.md` / `REPO_MAP.md` instead of duplicating them; both now tell the agent to record discoveries. |
| **`tests/` + `pyproject.toml`** (new) | 11 contract tests for `ArticleRepository` (dedup, idempotence, ID lookups) on in-memory SQLite. `pythonpath = ["."]` makes `python -m pytest` work from the repo root with no env juggling. `conftest.py` forces `DATABASE_URL=sqlite://` before importing `findata`, so no test can reach real Postgres. |
| **CI honesty** | Dropped `\|\| echo "No tests found yet"`; flake8 now covers `findata/` and `tests/`, not just the news package. |
| **`.claude/settings.json`** (new, checked in) | Shared allowlist for read-only commands and pytest; denies `alembic upgrade/downgrade`, `psql`, `git push`, and reading `.env`. Fewer prompts for safe work, a hard stop on the unsafe. |
| Stale-path fixes | `transformers/entity.py` docstrings, `pm-agent.yml`, `.env.example`, and a warning header on `docs/schema.sql`. |

## Still worth doing

1. **Package the repo** — a minimal `[project]` + `pip install -e .` removes the
   "must run from repo root" rule entirely, and lets the four `requirements.txt`
   files become optional-dependency groups. (REPO_REVIEW #11.)
2. **A drift guard in CI** — a job that greps tracked `*.md`, `*.py`, `*.yml` for
   the dead paths in REPO_MAP's false-trails table and fails on a hit. Doc drift
   is the failure mode this repo actually has; make it a test.
3. **Extend the tests to the pipeline and extractors** — `ExtractionPipeline`,
   `TransformationPipeline._persist()`, and the RSS extractor with a mocked
   `feedparser`. That is the verification loop for the sentiment work.
4. **Regenerate or delete `docs/schema.sql`** — a `make schema` target that dumps
   `Base.metadata` beats a hand-maintained file.
5. **Fix the malformed log call** in `ArticleRepository.insert_articles()`
   (see `docs/discoveries/004`).
6. **`findata/sources/news/requirements.txt` still offers "Option C: Claude API"**
   for sentiment, which contradicts the decision to score locally with FinBERT.
   Remove the option so agents don't pick it.
7. **Consider a `make demo` target** — one command that builds a scratch SQLite
   DB, runs the RSS extractor, and prints a summary. It doubles as the recruiter-
   facing "proof the pipelines run" and as an agent's end-to-end smoke check.
