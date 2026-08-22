# Testing Agent Instructions

You pick up GitHub Issues labelled `agent:testing status:ready` and write tests
for the **Resonance Desk** data-engine repo.

## Before you start

Read [`../../docs/REPO_MAP.md`](../../docs/REPO_MAP.md) (paths and invariants),
the "Write a test" section of [`../../docs/RECIPES.md`](../../docs/RECIPES.md),
and [`../../docs/discoveries/INDEX.md`](../../docs/discoveries/INDEX.md).

## Workflow

1. Read the issue — it names the module, the coverage expected, and where tests go.
2. Branch: `agent/<issue-number>-<short-description>`.
3. Write tests following the conventions below.
4. Verify: `python -m pytest` from the repo root.
5. Open a PR linked to the issue.

## Layout

`tests/` mirrors the source tree:

```
tests/
├── conftest.py                        # shared fixtures: engine, repo, sample_articles
└── findata/
    └── sources/
        └── news/
            ├── test_repository.py
            ├── test_pipeline.py
            ├── extractors/{test_rss.py,test_huggingface.py}
            └── transformers/{test_sentiment.py,test_entity.py}
```

## Database tests

- In-memory SQLite only. Use the `engine` / `repo` fixtures already defined in
  `tests/conftest.py` — don't re-create them per file, and never read `DATABASE_URL`.
- `article_tickers` has a composite PK `(article_id, ticker)`; duplicate inserts
  are silently skipped via `INSERT … ON CONFLICT DO NOTHING`, not raised.
- Worth covering: insert, deduplication (across batches *and* within one batch),
  `link_tickers`, `get_by_ticker`, `get_ids_by_urls`, `get_all`.

## Mocking external services

- RSS: mock `feedparser.parse()` with a canned feed dict.
- HuggingFace: mock `datasets.load_dataset()` with an iterable of row dicts.
- HTTP: `unittest.mock.patch`.
- Never hit a real endpoint, and never download a model in a test.

## Naming

Files `test_<module>.py`; functions `test_<behavior>()` —
`test_insert_articles_skips_duplicates`, `test_rss_strips_html`.

## What to cover

1. Happy path.
2. Edge cases — empty input, `None` content, missing optional fields.
3. Idempotence — re-running an insert or a transform changes nothing.
4. Error handling — malformed feeds, bad or missing dates.
