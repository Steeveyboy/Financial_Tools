# Recipes — how to add things to this repo

The single copy of these procedures. `CLAUDE.md`, `.github/copilot-instructions.md`
and `.github/agents/*.md` all point here; do not paste copies back into them.

Paths below are authoritative as of 2026-08-21 — see [`REPO_MAP.md`](REPO_MAP.md).

## Add a news extractor

1. Create `findata/sources/news/extractors/<name>.py`.
2. Subclass `ArticleExtractor` (`extractors/base.py`).
3. Set `source_id` — a unique short string, e.g. `"newsapi"`.
4. Implement `extract() -> list[dict]`. Each dict needs at minimum:
   - `url` (str) — canonical URL, the deduplication key
   - `title` (str)
   - `published_at` (datetime) — **must not be None**; the column is `NOT NULL`
   - optional: `author`, `publisher`, `content` (plain text, no HTML)
5. For large/streaming sources, override `extract_batches()` instead — see
   `extractors/huggingface.py` (FNSPID streams 15M rows in batches).
6. If the source already knows the tickers, add `mentioned_tickers: list[str]`
   and the pipeline links them at load time — no `EntityTransformer` needed.
7. Register it in `load_news_articles.py`.
8. Add dependencies to `findata/sources/news/requirements.txt`.
9. Add a test under `tests/findata/sources/news/` that mocks the network.

## Add a news transformer

1. Create `findata/sources/news/transformers/<name>.py`.
2. Subclass `ArticleTransformer` (`transformers/base.py`).
3. Set `transform_id` — a unique short string, e.g. `"sentiment"`.
4. Implement `transform(articles: list[dict]) -> list[dict]`:
   - add derived fields as new keys on each dict
   - handle `content is None` gracefully (set the derived field to `None`)
   - log a summary (count, min/max/mean)
5. Add a persistence branch for your `transform_id` in
   `TransformationPipeline._persist()` (`findata/sources/news/pipeline.py`).
6. New column? Add it to the model in `findata/models/` **and** write a migration.

## Add a table or column

1. Edit / create the model under `findata/models/` (one file per table,
   inheriting `findata.db.base.Base`).
2. New model file → import it in `findata/models/__init__.py` and add it to
   `__all__`. Alembic autogenerate only sees models reachable from that import.
3. From the repo root: `alembic revision --autogenerate -m "<message>"`.
4. **Read the generated migration before committing.** Autogenerate misses
   server defaults, dialect-specific indexes, and data backfills.
5. Migration files are named `NNNN_<slug>.py` — keep the numbering contiguous.
6. Do **not** run migrations against the user's live Postgres. Verify against
   SQLite (`DATABASE_URL=sqlite:///scratch.db`) or leave the command for the user.

## Write a test

- Location: `tests/` mirrors the package — `tests/findata/sources/news/test_repository.py`.
- Runner: `python -m pytest` from the repo root.
- Database: in-memory SQLite. Use the `repo` / `engine` fixtures in
  `tests/conftest.py`; never touch `DATABASE_URL`.
- Mock all external I/O — RSS feeds, HuggingFace, yfinance. No network in tests.
- Naming: files `test_<module>.py`, functions `test_<behavior>()`.

## Code style

- Type hints on every function signature; Google-style docstrings on public methods.
- Imports ordered stdlib → third-party → local.
- `logging` with a module-level `_logger`; never `print()`.
- No raw SQL outside the source's repository class.
