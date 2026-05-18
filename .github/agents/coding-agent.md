# Coding Agent Instructions

You are a coding agent working on the **Resonance Desk** financial tools repository. Your job is to pick up GitHub Issues labelled `agent:coding status:ready` and implement the requested feature.

## Workflow

1. Read the issue body carefully — it contains file paths, interface contracts, and acceptance criteria.
2. Create a branch named `agent/<issue-number>-<short-description>`.
3. Implement the change following the patterns below.
4. Write or update tests per the issue instructions.
5. Run `python -m pytest tests/ -v` to verify.
6. Open a PR linked to the issue.

## Implementing a New Extractor

1. Create `findata/sources/news/extractors/<name>.py`
2. Subclass `ArticleExtractor` from `extractors/base.py`
3. Set `source_id` (unique short string)
4. Implement `extract() -> list[dict]` with at minimum: `url`, `title`, `published_at`
5. For large/streaming sources, override `extract_batches()` (see `huggingface.py`)
6. Include `mentioned_tickers` in dicts if the source knows them
7. Add dependencies to `findata/sources/news/requirements.txt`

## Implementing a New Transformer

1. Create `findata/sources/news/transformers/<name>.py`
2. Subclass `ArticleTransformer` from `transformers/base.py`
3. Set `transform_id` (unique short string)
4. Implement `transform(articles: list[dict]) -> list[dict]`:
   - Add derived fields as new dict keys
   - Handle `None` content gracefully (set field to `None`)
   - Log a summary (min/max/mean or count)
5. Add persistence logic in `TransformationPipeline._persist()` for your `transform_id`
6. If a new DB column is needed, add it to the relevant model in `findata/models/` and create a new Alembic migration

## Schema Migrations

Schemas live as SQLAlchemy 2.0 ORM models under `findata/models/` (one file per table, all inheriting `findata.db.base.Base`). Migrations live in the single Alembic tree at `findata/db/migrations/`.

- Add new columns to the relevant ORM model in `findata/models/`
- Generate a migration: `alembic revision --autogenerate -m "<message>"` from the repo root
- Review the generated migration before committing — autogenerate misses some things (server defaults, dialect-specific indexes)
- For development quick-start, `python -m findata` runs `init_db()` (= `Base.metadata.create_all()` + seed exchanges); `alembic upgrade head` is the production path.

## Code Style

- Type hints on all function signatures
- Docstrings on all public methods (Google style)
- No raw SQL outside `ArticleRepository` (or the equivalent repository for other sources)
- Use `logging` (module-level `_logger`), never `print()`
- Keep imports sorted: stdlib → third-party → local

## Testing

- Tests go in `tests/findata/sources/news/` (or under the relevant source) mirroring the module structure
- Use `pytest` with `sqlite://` in-memory databases — pass `create_engine("sqlite://")` directly to `ArticleRepository(engine=…)`
- Mock all external I/O (HTTP calls, file reads, HuggingFace streaming)
- Name test files `test_<module>.py`, test functions `test_<behavior>()`
