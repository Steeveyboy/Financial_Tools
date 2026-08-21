# 001 — Nothing is installed: run everything from the repo root

- **Verified against:** commit `b675cfb` on 2026-08-21
- **Applies to:** every entry point, every test run

## What I found

There is no `pip install -e .` step and no `src/` layout. `findata` is importable
only because the current working directory is the repo root. The interpreter with
the dependencies is the in-tree venv at `./.venv/` (Python 3.12) — the system
`python` does not have SQLAlchemy.

`pyproject.toml` sets `pythonpath = ["."]` for pytest, so `python -m pytest`
resolves `findata` without any `PYTHONPATH` juggling. Ad-hoc scripts still need
the repo root as cwd.

## Why it bites

Running an entry point from inside `findata/` or `findata/sources/news/` fails
with `ModuleNotFoundError: No module named 'findata'`, which reads like a missing
dependency and sends you off installing things that are already there.

## What to do

- Always `cd` to the repo root first.
- Use the venv interpreter: `.venv/bin/python …` (or activate it).
- Prefer the `Makefile` targets — they encode the correct invocation.
- Don't "fix" an import error by adding `sys.path` hacks to source files.
