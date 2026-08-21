# Coding Agent Instructions

You implement GitHub Issues labelled `agent:coding status:ready` in the
**Resonance Desk** data-engine repo.

## Before you start

Read, in order: [`../../docs/REPO_MAP.md`](../../docs/REPO_MAP.md),
[`../../CLAUDE.md`](../../CLAUDE.md),
[`../../docs/RECIPES.md`](../../docs/RECIPES.md), and
[`../../docs/discoveries/INDEX.md`](../../docs/discoveries/INDEX.md).

The recipes for adding an extractor, a transformer, a table/column, or a test
live in `docs/RECIPES.md` and are **not duplicated here** — follow them there so
there is only one copy to keep correct.

## Workflow

1. Read the issue body — it carries the file paths, interface contract, and
   acceptance criteria.
2. Branch: `agent/<issue-number>-<short-description>`.
3. Implement, following `docs/RECIPES.md` and the invariants in `docs/REPO_MAP.md`.
4. Write or update tests per the issue.
5. Verify: `python -m pytest` from the repo root (in-memory SQLite; touches nothing real).
6. If you learned something non-obvious, add a note under `docs/discoveries/`
   and index it.
7. Open a PR linked to the issue.

## Hard rules

- No raw SQL outside a repository class.
- No `print()` — module-level `_logger`.
- Never run migrations or DDL against a live database; leave that command to the user.
- Don't touch `SentimentAnalysis/` (legacy).
