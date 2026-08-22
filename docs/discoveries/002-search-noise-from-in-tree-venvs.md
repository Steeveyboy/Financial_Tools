# 002 — Two venvs live in the working tree; `find .` is unusable

- **Verified against:** commit `b675cfb` on 2026-08-21
- **Applies to:** any search across the repo

## What I found

`./.venv/` and `./SentimentAnalysis/.venv/` are present in the working directory
(both gitignored, neither tracked). A bare `find . -name "*.py"` returns tens of
thousands of site-packages files before reaching any repo code.

`rg` and the Grep tool respect `.gitignore`, so they exclude both automatically.

## Why it bites

A single unscoped `find` or `ls -R` burns a large amount of context and buries
the actual answer, and the truncated output can make it look like repo files
don't exist.

## What to do

- Search with `rg` / Grep, not `find`.
- To enumerate real files: `git ls-files`.
- If `find` is genuinely needed, scope it to real directories:
  `find findata tests docs -type f`.
