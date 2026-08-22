# Discoveries — the agent field notebook

Non-obvious things learned by working in this repo: gotchas, invariants that
aren't visible in the code, commands that do/don't work, dead ends already
explored. The point is that the *next* agent does not re-derive them.

## When to write one

Write a note when you spent real effort learning something that the code alone
does not tell you, and it will still be true next week:

- a command failed in a way that wasn't obvious ("this needs `PYTHONPATH=.`")
- an invariant you had to reverse-engineer from three files
- a dead end ("tried X, doesn't work here because Y")
- a mismatch between what a doc says and what the code does
- data-shape surprises (a source's field is sometimes `None`, timezone-aware, …)

**Do not** write a note for: anything already in `REPO_MAP.md`, `RECIPES.md`, or
`CLAUDE.md`; a description of code that the code makes obvious; a task log or
progress report (those belong in the PR / commit message); anything that only
mattered inside one conversation.

## How to write one

1. Copy `_TEMPLATE.md` to `NNN-short-slug.md` (next free number).
2. Fill it in. Keep it under ~40 lines. One discovery per file.
3. **Add a line to `INDEX.md`** — a note that isn't indexed will not be found.
4. Record the commit SHA you verified against; that's how a future reader
   judges staleness.

## Maintenance

- If a note becomes wrong, fix it or delete it — a stale note is worse than none.
- If a note is something *everyone* needs every time, promote it into
  `REPO_MAP.md` / `RECIPES.md` and delete the note.
