# 001 — `findata` is not an installed package: run everything from the repo root

- **Verified against:** commit `b675cfb` on 2026-08-21
- **Applies to:** every entry point, every test run

## What I found

Dependencies are installed — the working environment is the **miniconda env
`finance`** (`conda activate finance`). What is *not* installed is this repo's
own package: there is no `pip install -e .`, no `[project]` table, no
`setup.py`. So `import findata` resolves only because the repo root happens to
be on `sys.path`, which in practice means the current working directory is the
repo root.

For pytest this is guaranteed by `pythonpath = ["."]` in `pyproject.toml`.
Ad-hoc scripts and `python -m …` invocations still depend on cwd.

Note the in-tree `./.venv/` directory. It is **not** the environment in use;
don't reach for `.venv/bin/python`.

## Why it bites

Running an entry point from inside `findata/` or `findata/sources/news/` fails
with `ModuleNotFoundError: No module named 'findata'`. That reads like a missing
dependency and sends you off installing packages that are already there, or
pointing at the wrong interpreter.

## What to do

- `conda activate finance`, then `cd` to the repo root before running anything.
- Prefer the `Makefile` targets — they encode the correct invocation.
- Don't "fix" an import error with `sys.path` hacks in source files; fix the cwd.
- The real fix is packaging the repo (`pip install -e .`) — see
  `docs/AGENT_HABITAT.md`, "Still worth doing" #1, and REPO_REVIEW #11.
