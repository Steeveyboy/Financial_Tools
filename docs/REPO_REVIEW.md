# Repo Review — August 2026

Scope: full review of the repository against its stated purpose — a time-series
financial + news warehouse that **backfills** history and **continuously
updates**, presentable as a portfolio piece. Each finding is weighed by impact
and difficulty. Companion to [CLEANUP_PLAN.md](docs/CLEANUP_PLAN.md), which remains
the structural roadmap; this document covers correctness, product gaps, and
presentation.

## Summary verdict

The architecture is genuinely good: one ORM `Base`, one Alembic tree, a clean
two-phase news ETL with a single repository layer, dialect-aware upserts, and
docstrings well above hobby-project standard. The three things holding it back:

1. **Zero tests, and CI is wired so tests can never fail** — the single
   biggest credibility gap for a portfolio repo.
2. **The "continuously updating" claim isn't true yet** — nothing is
   scheduled, and the transform phase (sentiment) is a stub, so the pipeline
   ends at raw article storage.
3. **A handful of real bugs** in the ingestion paths (ticker-link data loss,
   a datetime crash in date-bounded FNSPID backfills, broken Makefile
   targets) plus documentation that has drifted behind the code.

Priorities below are ordered by leverage: P0 = correctness/trust, P1 = make
the product claim true, P2 = structure & polish, P3 = the demo layer.

---

## P0 — Correctness and trust

### 1. Test suite + honest CI  — Impact: HIGH · Difficulty: MEDIUM (~1–2 days)

There is no `tests/` directory anywhere, yet `.github/workflows/ci.yml` runs:

```yaml
python -m pytest tests/ -v --tb=short || echo "No tests found yet"
```

The `|| echo` means the step **succeeds even when tests fail**, so the green
badge is unearned. Any reviewer who opens the workflow file sees this.

Fix:
- Remove the `|| echo` escape hatch.
- Add `tests/` with pytest against in-memory SQLite (the repository layer
  already accepts an injected engine — it was designed for this):
  - `ArticleRepository`: URL dedup within batch and across batches,
    `bulk_link_tickers` idempotency, `get_by_ticker` ordering.
  - Extractor unit tests with fixture data: RSS date parsing (RFC 2822 + ISO
    8601), FNSPID `_normalise` / `_passes_filters`.
  - `DailyOHLCV` insert/skip-existing round-trip.
  - Alembic: `alembic upgrade head` against empty SQLite == `Base.metadata`.
- Lint the whole `findata/` package, not just `findata/sources/news/`.

### 2. Ticker links silently dropped for duplicate-URL batches — Impact: HIGH · Difficulty: LOW (~1 hour)

`ExtractionPipeline._run_extractor`:

```python
num_inserted = self.repo.insert_articles(batch)
if num_inserted:
    self._link_known_tickers(batch)
```

FNSPID repeats the same URL under multiple tickers. When every article in a
batch is already in the DB (`num_inserted == 0`) — common on re-runs and when
a URL's other tickers land in a later batch — `_link_known_tickers` is never
called and those `(article_id, ticker)` rows are **lost**. The links are the
whole point of the table, and the insert is already idempotent
(`ON CONFLICT DO NOTHING`), so the guard buys nothing.

Fix: call `_link_known_tickers(batch)` unconditionally.

### 3. FNSPID date filtering crashes: aware vs naive datetimes — Impact: HIGH · Difficulty: LOW (~1 hour)

`huggingface.py::_parse_date` returns `dt.replace(tzinfo=timezone.utc)`
(timezone-**aware**, despite the docstring saying naive), while
`self.start_date` / `self.end_date` come from `datetime.strptime` (naive).
`_passes_filters` then evaluates `pub_date < self.start_date` →
`TypeError: can't compare offset-naive and offset-aware datetimes` — every
date-bounded backfill (`--start-date`/`--end-date`) dies on the first row with
a parseable date.

Also inconsistent with the RSS extractor (naive UTC) and the `articles`
schema (`DateTime` without timezone).

Fix: pick one convention — naive UTC matches the current schema — and
enforce it in both extractors. Longer-term (P2) consider
`DateTime(timezone=True)` everywhere, as `companies` already does.

### 4. `articles.published_at` is NOT NULL but extractors can produce None — Impact: MEDIUM · Difficulty: LOW (~1 hour)

Both `_parse_date` implementations return `None` on unparseable/missing
dates, and RSS entries may lack `published` entirely. The bulk
`session.execute(insert(Article), clean_rows)` then raises `IntegrityError`,
killing the **entire 500-row batch**, not just the bad row.

Fix: either make the column nullable (a real fraction of feed data has no
timestamp), or drop-and-log rows without `published_at` before insert. Add a
test.

### 5. Broken/false entry points — Impact: MEDIUM · Difficulty: LOW (~1–2 hours)

- `Makefile` `market-data` runs `cd market_data && python fetch_stock_data.py`
  — `market_data/` no longer exists (ported to `findata/sources/market/` in
  PR #14). The documented command in README fails immediately.
- `make news-fnspid TICKERS="AAPL MSFT"` silently **ignores** `TICKERS`, and
  `load_news_articles.py` advertises `--tickers` in its docstring but never
  defines the argument — so a ticker-filtered FNSPID backfill (the documented
  workflow) is impossible from the CLI. `FNSPIDExtractor` supports it; it's
  just not wired through.
- `load_news_articles.py` builds its own engine via
  `create_engine(get_db_url())` instead of `findata.db.session.get_engine()`,
  so there are two competing config paths (news `config.py` raises without
  `DATABASE_URL`; `findata.config` falls back to SQLite).

Fix: repoint the Makefile at `python -m findata.sources.market.fetch_stock_data`,
add `--tickers` to the arg parser and pass `$(TICKERS)` through, and use the
shared engine. Delete `findata/sources/news/config.py` in favour of
`findata.config` + a `NEWS_LOG_LEVEL` read.

---

## P1 — Make "backfilling and continuously updating" true

### 6. Implement the sentiment transform end-to-end — Impact: VERY HIGH · Difficulty: MEDIUM-HIGH (~2–4 days)

The transform phase is the differentiator of the whole design (two-phase ETL
so transforms re-run retroactively), yet today:
`SentimentTransformer.transform()` is a stub, `TransformationPipeline` is
never invoked by any entry point, `_persist()` has no sentiment branch, and
`get_untransformed()` returns everything with a warning.

Plan (matches the options already documented in `transformers/sentiment.py`):
1. Migration `0004`: `articles.sentiment_score FLOAT NULL` + `transform_log`
   table (`article_id`, `transform_id`, `applied_at`, PK on the pair).
2. Implement `get_untransformed()` as an anti-join against `transform_log`,
   batched via the existing `yield_per` pattern (the table is ~millions of
   rows; `get_all()` must not be the path).
3. FinBERT (`ProsusAI/finbert`) for scoring — free, financial-domain,
   defensible in an interview. Batch inference, skip empty content.
4. `_persist()` branch for `sentiment` writing scores + log rows in one
   session; a `transform_news.py` entry point / `make transform` target.

This turns "I store news articles" into "I compute a sentiment time series
over 15M financial headlines and can re-run any transform retroactively" —
the strongest talking point available in this codebase.

### 7. Incremental OHLCV updates — Impact: MEDIUM-HIGH · Difficulty: LOW-MEDIUM (~half a day)

`fetch_stock_data.py` defaults to re-downloading **10 years** per ticker on
every run, then discards already-present dates via `_existing_dates()` (a
full per-ticker date scan). Correct, but wasteful and slow — the opposite of
"continuously updating".

Fix: add an `--update` mode that queries `MAX(date)` per ticker and fetches
only from there; keep full-range mode for first-time backfill. Also verify
the `df.index.isin(existing)` comparison with a test — it compares pandas
`Timestamp`s against `datetime.date`s from the DB, which works on current
pandas but is exactly the kind of silent-mismatch that deserves a pin. On
SQLite, `to_sql` writes full timestamps into the `DATE` column (type fidelity
worth a test as well).

### 8. Scheduled ingestion — Impact: HIGH · Difficulty: MEDIUM (~1 day + a free Postgres)

Nothing runs on a schedule, so the database only updates when someone runs a
script by hand. The cheapest credible setup:

- Hosted Postgres free tier (Neon / Supabase), `DATABASE_URL` as a GitHub
  Actions secret.
- One workflow, two cron jobs: RSS extraction hourly-ish; OHLCV `--update`
  nightly after market close; transform step after extraction.
- The workflow run history then *is* the proof that the pipeline is live —
  visible on the repo without deploying anything.

Note: `ExtractionPipeline.run()` calls `create_tables()` on every run —
harmless, but production path should be `alembic upgrade head` in the
workflow, with `create_tables()` kept for tests only.

### 9. RSS source quality — Impact: MEDIUM · Difficulty: MEDIUM

The module docstring and README still say "Reuters Business RSS", but the
Reuters feed is dead; actual defaults are Yahoo Finance RSS + a Google News
query. Two consequences worth addressing:
- Google News entry URLs are `news.google.com` redirect links — they work as
  dedup keys but aren't canonical, so the same story via another feed won't
  dedup, and `publisher` gets stamped with the Google News feed title.
  Resolve redirects to canonical URLs (or at least record the real outlet).
- RSS `mentioned_tickers` are never populated, so live articles get no ticker
  links until an entity transformer exists — meaning the "news per ticker"
  query only works for the historical dataset. A cheap dictionary-lookup
  entity transformer against the `companies` table would close the loop.

---

## P2 — Structure, hygiene, docs

### 10. Finish cleanup Phases 4–5; drop the 31 MB JSON — Impact: MEDIUM · Difficulty: LOW-MEDIUM

- `descriptions/company_info.json` is **31 MB of committed data** (append-only
  concatenated JSON). Move loader to `findata/sources/corporate/`, keep a
  ~10-record sample fixture, delete the blob (history rewrite optional — do
  it now if ever, before the repo gets forks).
- `SentimentAnalysis/` (9 MB, pickles + CSVs) → `legacy/` per Phase 5.
- Both are already planned in CLEANUP_PLAN; they're just the difference
  between a 50 MB clone and a 5 MB one.

### 11. Packaging and tooling — Impact: MEDIUM · Difficulty: MEDIUM (~1 day)

Four separate `requirements.txt` files and no installable package. A single
`pyproject.toml` with extras (`[news]`, `[market]`) and console scripts
(`findata-init`, `findata-news`, `findata-market`), plus `ruff` +
`pre-commit` (and mypy if ambitious — the type hints are already there),
reads as professional engineering at a glance. Phase 7 of the cleanup plan;
worth pulling forward.

### 12. Documentation drift — Impact: MEDIUM · Difficulty: LOW (~2 hours)

The docs say Phase 3 is pending; the code says it shipped (PR #14):
- README/CLAUDE.md still list `market_data/` and `descriptions/` as
  top-level modules and "pre-port"; `market_data/` doesn't exist.
- CLEANUP_PLAN status line says "Phases 0, 1, and 2 done" — Phase 3 is done.
- `docs/schema.sql` has no `daily_ohlcv` table (the regeneration command is
  right there in its header — add it as `make schema` and run it in CI so it
  can't drift again).
- News README/docstrings still describe Reuters RSS and FNSPID "streaming
  mode" (`load_dataset(..., streaming=False)` since commit `7a4c119`).

Stale docs are cheap to fix and expensive to be caught with.

### 13. Portfolio-surface basics — Impact: MEDIUM · Difficulty: LOW (~2 hours)

- **No LICENSE file** — public repo, add MIT.
- README: add CI badge, a mermaid architecture/ER diagram, a "what this
  demonstrates" paragraph (2-phase ETL, single migration history,
  dialect-aware upserts, 15M-row backfill), and one screenshot/GIF once the
  dashboard (below) exists. Recruiters spend 90 seconds on the README; spend
  effort accordingly.

---

## P3 — The demo layer

### 14. Small Streamlit dashboard — Impact: VERY HIGH (for the stated goal) · Difficulty: MEDIUM (~1–2 days)

`streamlit` is already in `findata/sources/market/requirements.txt` but
unused. A single-page app — pick a ticker → price chart with news-volume
bars and sentiment overlay, powered entirely by warehouse queries — converts
"a repo of ETL scripts" into "a live data product" and gives every
conversation a visual anchor. Deployable free on Streamlit Community Cloud
against the hosted Postgres. Do this **after** P1 items 6–8 so it has real,
fresh data to show.

### 15. Later / roadmap

- SEC/XBRL ingestion (Phase 6) — biggest scope item; keep on the roadmap,
  don't block the showcase on it.
- Real FKs `daily_ohlcv.ticker` / `article_tickers.ticker` → `companies`
  (the open coupling-vs-integrity question in CLEANUP_PLAN).
- Timezone-aware timestamps across `articles` / `daily_ohlcv`.
- `Insider` ingestion or drop the stub table.

---

## Suggested sequencing

| Order | Item | Impact | Difficulty |
|---|---|---|---|
| 1 | Bug fixes #2 #3 #4 #5 (one PR) | High | Low |
| 2 | Test suite + honest CI (#1) | High | Medium |
| 3 | Sentiment transform end-to-end (#6) | Very high | Medium-High |
| 4 | Incremental OHLCV (#7) | Medium-High | Low |
| 5 | Scheduled ingestion vs hosted Postgres (#8) | High | Medium |
| 6 | Docs sync + LICENSE + README polish (#12, #13) | Medium | Low |
| 7 | Streamlit dashboard (#14) | Very high | Medium |
| 8 | Repo slimming Phases 4–5 (#10) | Medium | Low-Medium |
| 9 | pyproject + ruff/pre-commit (#11) | Medium | Medium |
| 10 | RSS canonicalisation + entity transformer (#9) | Medium | Medium |

Items 1–7 are roughly two focused weeks and take the repo from "promising
mid-migration codebase" to "live, tested, continuously-updating financial
warehouse with a demo" — which is the story worth telling.
