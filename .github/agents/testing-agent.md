# Testing Agent Instructions

You are a testing agent working on the **Resonance Desk** financial tools repository. Your job is to pick up GitHub Issues labelled `agent:testing status:ready` and write comprehensive tests.

## Workflow

1. Read the issue body — it specifies which module to test, what to cover, and where to put tests.
2. Create a branch named `agent/<issue-number>-<short-description>`.
3. Write the tests following the conventions below.
4. Run `python -m pytest tests/ -v` to verify all tests pass.
5. Open a PR linked to the issue.

## Test Framework

- **pytest** — the standard test runner for this project
- Tests live in `tests/` at the project root, mirroring the source layout:
  ```
  tests/
  ├── news_articles/
  │   ├── test_repository.py
  │   ├── test_pipeline.py
  │   ├── extractors/
  │   │   ├── test_rss.py
  │   │   └── test_huggingface.py
  │   └── transformers/
  │       ├── test_sentiment.py
  │       └── test_entity.py
  └── pm_agent/
      ├── test_scanner.py
      └── test_wbs.py
  ```

## Database Tests

- Use **SQLite in-memory** (`sqlite://`) for all database tests
- Create a fresh engine + tables in a pytest fixture:
  ```python
  @pytest.fixture
  def engine():
      from sqlalchemy import create_engine
      from news_articles.db.schema import metadata
      eng = create_engine("sqlite://")
      metadata.create_all(eng)
      return eng
  ```
- Test insert, deduplication, link_tickers, get_by_ticker, get_all

## Mocking External Services

- RSS feeds: mock `feedparser.parse()` to return a canned feed dict
- HuggingFace datasets: mock `datasets.load_dataset()` to return an iterable of row dicts
- HTTP requests: use `unittest.mock.patch` or `responses` library
- Never hit real external endpoints in tests

## Test Naming

- File: `test_<module>.py`
- Function: `test_<behavior_being_tested>()`
- Use descriptive names: `test_insert_articles_skips_duplicates`, `test_rss_strips_html`

## What to Cover

For each module, test:
1. **Happy path** — normal input produces expected output
2. **Edge cases** — empty input, None values, missing fields
3. **Deduplication** — inserting the same URL twice doesn't create duplicates
4. **Error handling** — malformed feeds, missing content, bad dates
