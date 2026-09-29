# FNSPID Medallion Pipeline — Requirements

**Status:** Draft for review · **Author:** agent session, 2026-09-29 · **Verified against:** commit `0b37b1b`

Requirements for re-ingesting the FNSPID news dataset through **DuckDB + dbt**
into a staging table, then refining it through a minimal **bronze → silver →
gold** medallion before it reaches the Postgres warehouse. This document says
*what* must be true when the work is done and *why*. It does not contain code.
Decisions that belong to the user are collected in §13 and must be answered
before implementation starts.

Companion documents: [`REPO_MAP.md`](REPO_MAP.md) (paths),
[`DATA_MODEL.md`](DATA_MODEL.md) (the naming standard gold must obey),
[`discoveries/006`](discoveries/006-fnspid-csv-type-inference.md) (why the
current FNSPID load is fragile), [`SENTIMENT_TRANSFORM.md`](SENTIMENT_TRANSFORM.md)
(the downstream consumer).

---

## 1. Why

The current path is `FNSPIDExtractor` (HuggingFace `datasets`) →
`ExtractionPipeline` → `ArticleRepository` → Postgres, row by row in Python.
This work **changes how FNSPID is loaded** (§5.1). The current path has three
structural problems:

| Problem | Evidence |
|---|---|
| **Type inference is fought, not avoided.** pandas guesses column types per chunk and crashes ~1.4M rows in; the workaround is a hand-maintained per-file schema. | discovery 006 |
| **Every re-run re-downloads and re-parses 15.7M rows** to change one cleaning rule. There is no persisted intermediate; cleaning logic lives inside `_normalise()`. | `extractors/huggingface.py` |
| **Dedup and linking happen at insert time, batch by batch**, so correctness depends on batch boundaries (REPO_REVIEW #2: links dropped when a URL's other tickers land in a later batch). | `docs/REPO_REVIEW.md` #2 |

A columnar, set-based pipeline fixes all three: DuckDB reads the CSVs as
all-`VARCHAR` in one statement, dedup is a single `GROUP BY url` over the
whole dataset instead of per batch, and each layer is persisted so a rule
change re-runs one dbt model, not a 15.7M-row download.

It is also a portfolio piece (CLAUDE.md "Current Priorities" #1): dbt lineage,
tests and docs are *visible proof the pipeline runs*.

## 2. Scope

### In scope

- Landing the two FNSPID news CSVs locally, once.
- A dbt project (adapter `dbt-duckdb`) that builds bronze, silver and gold
  layers in a local DuckDB file.
- Enrichment of FNSPID data that can be computed **from FNSPID itself** plus,
  optionally, the warehouse's existing `market.daily_bars` / `reference.companies`
  (§7).
- A publish step that loads gold into `news.articles` / `news.article_securities`
  through the existing `ArticleRepository`.
- dbt tests, a pytest that runs the dbt project over a fixture CSV, and
  commands for the user to run the real thing.

### Out of scope (non-goals)

- **Sentiment scoring.** Stays the Python FinBERT transform over `news.articles`
  (non-negotiable: local FinBERT, see `SENTIMENT_TRANSFORM.md`). Gold only
  *prepares* text for it.
- **RSS.** Live feeds keep the current `RSSExtractor` path. This is a batch
  pipeline for a static historical dataset.
- **Incremental/streaming loads.** FNSPID is a fixed 1999–2023 snapshot; full
  refresh is the correct and simplest strategy (NFR-4).
- **Orchestration** (Airflow, Dagster, cron). Make targets are enough.
- **Replacing Postgres as the serving store.** DuckDB is the processing engine;
  Postgres remains the warehouse the demo reads.
- **FNSPID's `Stock_price/` files.** Price data already comes from
  `findata/sources/market/` (yfinance). See Q7.
- Changes to `legacy/SentimentAnalysis/`.

## 3. Constraints inherited from the repo

These are the CLAUDE.md non-negotiables and how this design honours each. Any
requirement below that conflicts with one of these is wrong.

| Non-negotiable | How this pipeline complies |
|---|---|
| One `Base`, one Alembic tree | DuckDB layers are **not** warehouse tables and get no ORM models or migrations. The Postgres tables the pipeline writes (`news.articles`, `news.article_securities`) already exist in `0001_baseline.py`; this work adds **no** Postgres DDL unless Q5 decides otherwise. |
| No raw SQL outside a repository class | dbt model files are the declared exception — they *are* the transform layer, not Python-embedded SQL. Python code that reads gold goes through one new repository-style class (FR-P2). Python code that writes Postgres goes through `ArticleRepository`. See Q2. |
| `logging` with `_logger`, never `print()` | Applies to all new Python (download, publish). dbt's own console output is dbt's. |
| Don't run migrations/DDL against the user's Postgres | The dbt project **never** attaches the user's Postgres with write access. The only Postgres writes are the publish step, which the user runs. |
| Naming standard (`DATA_MODEL.md` §1) | Gold columns use warehouse names: `symbol` not `ticker`, `published_at` (UTC instant), `*_date` for calendar dates, `is_*` booleans. Bronze keeps source names verbatim; silver is where renaming happens. |

## 4. Source data — what is known

Facts established by earlier work (discovery 006, the extractor, the
`inspect_fnspid` notebook). Anything marked *verify* must be profiled in the
first implementation step (FR-B5) before silver rules are finalised.

| Fact | Consequence |
|---|---|
| HF repo `Zihan1004/FNSPID`; news is two CSVs: `Stock_news/nasdaq_exteral_data.csv` (sic) and `Stock_news/All_external.csv` | Two landing files, one bronze table |
| Headers differ: the nasdaq file has a leading `Unnamed: 0` pandas index column | Union **by name**, not position |
| Columns: `Date, Article_title, Stock_symbol, Url, Publisher, Author, Article, Lsa_summary, Luhn_summary, Textrank_summary, Lexrank_summary` | Bronze keeps all of them |
| ~15.7M rows total; spans 1999–2023 | Multi-GB; must not be materialised in pandas (NFR-1) |
| Blank-early columns cause type-inference crashes | Read everything as `VARCHAR` (FR-B2) |
| `Date` looks like `2020-06-05 06:30:54 UTC`; several other formats handled by `_DATE_FORMATS` | Silver parses with an ordered format list; unparseable → reject |
| The same `Url` repeats under multiple `Stock_symbol`s | Silver splits into one-row-per-URL + URL×symbol bridge |
| Only the nasdaq file carries `Article` bodies (the extractor loads it first so URL dedup keeps the body) | Silver's survivor rule must prefer the row **with** a body, deterministically — not "whichever loaded first" |
| `Url` can be blank | Rejected: URL is the warehouse dedup key |
| Symbol casing — *verify* | Upper-case in silver regardless (warehouse `CHECK symbol = upper(symbol)`) |
| Fraction of rows with a body / with summaries — *verify* | Drives Q6 |

Drift noted while researching: discovery 006 says `_iter_rows` loads with
`streaming=True`, but the code at `0b37b1b` passes `streaming=False`. With
`streaming=False`, `datasets` converts the whole file to Arrow before returning
a single row. The new load path in §5.1 replaces this code rather than fixing it.

## 5. Architecture

```
                 ┌──────────────────── DuckDB file: data/lakehouse/fnspid.duckdb ────────────────────┐
HF Hub           │                                                                                   │
 Zihan1004/FNSPID│  BRONZE (staging)            SILVER (clean, conform)        GOLD (enrich, serve)  │
  ──download──►  │  bronze.fnspid_news_raw ──►  silver.fnspid_articles    ──►  gold.news_articles    │ ──publish──► Postgres
 data/raw/fnspid │   all VARCHAR, + lineage     silver.fnspid_article_          gold.news_article_    │  (ArticleRepository)
   *.csv         │                               symbols                        securities           │   news.articles
 (landing,       │                             silver.fnspid_rejects           gold.symbol_daily_news│   news.article_securities
  immutable)     │                                                                                   │
                 └───────────────────────────── built by `dbt build` (dbt-duckdb) ────────────────────┘
```

### 5.1 How loading changes, and where streaming belongs

This work **replaces** the FNSPID load path; it does not sit beside it.

| | Today | After |
|---|---|---|
| Fetch | HF `datasets.load_dataset()` per CSV, parsed row by row in Python | Raw CSV bytes downloaded once to `data/raw/fnspid/` |
| Parse / type | pandas inside the `datasets` CSV builder, fought with an all-string `Features` schema | DuckDB `read_csv(all_varchar=true, union_by_name=true)` |
| Clean / dedup / link | `_normalise()` + per-batch `insert_articles()` | dbt models over the whole dataset |
| Write to Postgres | Every scanned row goes through Python | Only gold rows, already deduplicated, in batches |
| Entry point | `load_news_articles.py --fnspid` → `FNSPIDExtractor` | `load_news_articles.py --fnspid` → `FNSPIDGoldExtractor` (FR-P6) |

**Streaming decision.** Streaming is needed at two boundaries and not in the
middle:

1. **Download: streamed to disk (required).** The files are multi-GB and must
   never be held in memory. `huggingface_hub` writes to disk in chunks and can
   resume an interrupted download (FR-L5). HF `datasets` streaming mode is
   **dropped**: it only existed to feed Python row by row, and its per-chunk
   type inference caused discovery 006.
2. **Bronze build: no streaming needed.** DuckDB reads the CSVs in parallel
   chunks and spills to disk when it runs short of memory, so it never needs the
   whole file in RAM. Loading the landed files beats streaming from the Hub
   (`hf://` paths): every full rebuild would otherwise download everything again,
   and the build would need the network. `hf://` is kept as a documented
   fallback for machines without the disk space (Q10).
3. **Publish: streamed out of DuckDB (required).** Gold is read with a cursor in
   fixed-size batches (`fetchmany` or Arrow record batches), never with
   `fetchall()`/`.df()` over the full table, so publish memory depends on batch
   size and not on dataset size (FR-P7).

Layer contract, in one line each:

- **Landing** — the source files, byte-for-byte. Never edited. Re-downloadable.
- **Bronze** — the staging table: every source row, every column, as text, plus
  where it came from. No filtering, no casting. Answers "what did the source say?"
- **Silver** — typed, cleaned, de-duplicated, conformed to warehouse naming.
  Rejected rows are kept with a reason, not dropped. Answers "what is true?"
- **Gold** — shaped for consumers: the exact contract of the Postgres tables,
  plus enrichments and aggregates. Answers "what do consumers need?"

"Minimalistic" means: three layers, no intermediate/ephemeral sprawl, no
snapshots, no seeds unless an enrichment needs a lookup table, and a model
count small enough to read in one sitting (target ≤ 8 models).

## 6. Functional requirements

### 6.1 Landing

- **FR-L1** A Python command downloads the two news CSVs from the HF Hub into
  `data/raw/fnspid/` (path configurable). Uses `huggingface_hub` so the HF
  cache and auth token are reused.
- **FR-L2** Download is idempotent: an existing complete file is not
  re-downloaded. A checksum/size manifest is written beside the files.
- **FR-L3** `data/` is git-ignored. No dataset bytes are ever committed.
- **FR-L4** Landing is the only step that needs the network. Every later step
  runs offline.
- **FR-L5** The download streams to disk and can resume. Memory use is constant
  whatever the file size. A partly downloaded file is never passed to bronze:
  the manifest is written only once the size/checksum check passes.
- **FR-L6** Before downloading, the command checks free disk space against the
  expected file sizes and stops with a clear message if there isn't enough.

### 6.2 Bronze — the staging table

- **FR-B1** One dbt model, `bronze.fnspid_news_raw`, materialised as a **table**,
  built by DuckDB's `read_csv` over the landing glob.
- **FR-B2** All columns read as `VARCHAR` (`all_varchar=true`). No type
  inference anywhere. This is the structural fix for discovery 006.
- **FR-B3** Files unioned **by name** (`union_by_name=true`) so the differing
  headers need no per-file schema. `Unnamed: 0` is kept (as `source_row_index`
  or similar), not dropped — it is lineage.
- **FR-B4** Lineage columns added: source file name, 1-based row number within
  the file, and the dbt run's load timestamp. Together (file, row) is unique.
- **FR-B5** A profiling query/analysis (a dbt `analysis` or a notebook) reports
  per-column null/blank rates, distinct `Date` formats, symbol casing, and URL
  duplication. Its output is recorded in a discovery note before silver rules
  are frozen.
- **FR-B6** Bronze row count equals the sum of source data rows. A dbt test
  asserts it against the landing manifest.
- **FR-B7** Malformed CSV lines are **not silently skipped**: either the read
  is strict, or rejected lines are captured (`store_rejects`) and counted. The
  count must be visible after a run.

### 6.3 Silver — clean and conform

- **FR-S1** Trim whitespace; convert empty strings to `NULL` on every text column.
- **FR-S2** Parse `Date` to a UTC `timestamptz` `published_at`: strip a
  trailing ` UTC`, try the same ordered formats as `_DATE_FORMATS`, treat
  offset-less values as UTC (matching `findata.db.types.ensure_utc`).
- **FR-S3** Normalise `symbol`: trimmed, upper-cased, validated against a
  pattern that admits share-class suffixes (`BRK.B`); length ≤ 32.
- **FR-S4** Normalise `url`: trimmed; scheme and host lower-cased. **Path and
  query are left untouched** unless Q4 decides otherwise, because changing the
  dedup key changes which Postgres rows already match.
- **FR-S5** `silver.fnspid_articles`: exactly **one row per `url`**. Survivor
  rule, deterministic and documented: prefer a row with a non-null body, then
  the longest title, then the earliest `published_at`, then lowest
  (file, row) lineage as the final tie-break. Output columns follow
  `news.articles` naming: `url, title, author, publisher, content,
  published_at`, plus the summary columns and lineage of the surviving row.
- **FR-S6** `silver.fnspid_article_symbols`: distinct `(url, symbol)` pairs from
  **all** bronze rows, not just survivors. This is the set-based fix for
  REPO_REVIEW #2 — no link can be lost to a batch boundary.
- **FR-S7** `silver.fnspid_rejects`: every bronze row excluded from silver, with
  its lineage and a machine-readable `reject_reason` (`missing_url`,
  `unparseable_date`, `invalid_symbol`, …). A row rejected for its symbol but
  with a valid URL/date still contributes an article — rejection is per output,
  not per row. (Exact semantics: Q3.)
- **FR-S8** Conservation check: every bronze row is accounted for — it
  contributes to `fnspid_articles` (as survivor or duplicate) or appears in
  `fnspid_rejects`. Enforced by a dbt test.

### 6.4 Gold — enrich and serve

Gold has two jobs: match the Postgres contract exactly, and add value that is
cheap in DuckDB and expensive later.

- **FR-G1** `gold.news_articles` has exactly the columns `ArticleRepository.insert_articles()`
  accepts (`url, title, author, publisher, content, published_at`) with
  `ingest_source = 'fnspid'`, plus the enrichment columns of FR-E*. Columns that
  do not exist in `news.articles` are carried in gold but not published unless
  Q5 adds them.
- **FR-G2** `gold.news_article_securities`: `(url, symbol, link_source =
  'extractor')` — the same `link_source` the current extractor path writes,
  since the symbol is still source-asserted.
- **FR-G3** `gold.symbol_daily_news`: one row per `(symbol, trade_date)` with
  article count, distinct-publisher count, share of articles with a body. This
  is the demo-facing aggregate ("news volume around a price move") and needs no
  Postgres schema change — it can be exported as Parquet or queried directly.
- **FR-G4** Gold names obey `DATA_MODEL.md` §1 so the publish step is a
  straight mapping with no renames.

### 6.5 Enrichment (computed in silver or gold)

MVP — derivable from FNSPID alone:

- **FR-E1** `url_domain` — host of the URL, `www.` stripped. Publisher is
  blank for many rows; the domain is a reliable fallback.
- **FR-E2** `publisher_normalised` — publisher, else a domain→publisher mapping
  (a small dbt seed), else the domain. Collapses spelling variants.
- **FR-E3** `trade_date` — the trading session a headline can first affect:
  convert `published_at` to `America/New_York`; if at/after 16:00 ET or on a
  non-trading day, roll forward to the next trading day. This is the join key
  to `market.daily_bars.trade_date` and the single most important enrichment
  for the "does tone predict price" question. Calendar source: Q7.
- **FR-E4** Text features: `title_length`, `content_length`, `is_body_present`,
  `symbol_count` (how many symbols the URL is linked to — multi-symbol articles
  are weaker per-symbol signals).
- **FR-E5** `sentiment_text` — the exact text FinBERT will score, built with the
  rule already in `SENTIMENT_TRANSFORM.md` ("headline leads": `title. content`,
  falling back to whichever exists). Precomputing it makes the Python transform
  a pure read. Whether it is published: Q5.

Stretch — needs the warehouse (read-only attach, Q7):

- **FR-E6** `sector` / `industry` from `reference.companies` on `symbol`.
- **FR-E7** Forward returns (`return_1d`, `return_5d`) from
  `market.daily_bars.adj_close` on `(symbol, trade_date)`, for
  `gold.symbol_daily_news`. Uses `adj_close`, never `close` (DATA_MODEL §2).

### 6.6 Publish to Postgres

- **FR-P1** A Python command loads gold into Postgres via the existing
  `ExtractionPipeline` / `ArticleRepository` path. Preferred shape: a new
  `ArticleExtractor` subclass (e.g. `FNSPIDGoldExtractor`, `ingest_source =
  "fnspid"`) whose `extract_batches()` pages through `gold.news_articles` and
  attaches each article's symbols as `mentioned_symbols`. This reuses URL dedup,
  `ON CONFLICT DO NOTHING` linking and the existing tests — zero new Postgres SQL.
- **FR-P2** The DuckDB reads behind FR-P1 live in one small repository-style
  class (e.g. `LakehouseRepository`), keeping "no raw SQL outside a repository
  class" true for Python.
- **FR-P3** Publish is re-runnable: a second run inserts zero articles and zero
  links, and reports that.
- **FR-P4** Publish supports the same filters as today (`--TICKERS`,
  `--start-date`, `--end-date`) pushed down into the DuckDB query, not applied
  in Python.
- **FR-P5** Publish takes its target from `DATABASE_URL` like every other
  entry point; it works against SQLite for local verification.
- **FR-P6** `load_news_articles.py --fnspid` and `make news-fnspid` switch to
  the gold-backed extractor. When gold is missing, they fail with a message
  naming the commands to build it, rather than falling back to the old path.
  `--TICKERS` reaches the extractor from the Makefile too (REPO_REVIEW: the
  target currently drops it).
- **FR-P7** Publish reads gold in fixed-size batches (§5.1 point 3) and
  deduplicates nothing itself. Each batch is ready to insert as it arrives.
- **FR-P8** Once acceptance criterion 5 passes, the HF `datasets` path
  (`FNSPIDExtractor._iter_rows`, `_DATA_FILES`, the `datasets` dependency if
  nothing else uses it) is removed. Discovery 006 is then marked superseded,
  not deleted.

## 7. Data quality — required dbt tests

| Model | Tests |
|---|---|
| `bronze.fnspid_news_raw` | `(source_file, source_row_number)` unique; row count = manifest (FR-B6) |
| `silver.fnspid_articles` | `url` unique + not null; `published_at` not null; `published_at` within 1990-01-01 … 2024-12-31 (range per §4, adjust after profiling) |
| `silver.fnspid_article_symbols` | `(url, symbol)` unique; `symbol` = upper(symbol); `url` relationship → `silver.fnspid_articles` |
| `silver.fnspid_rejects` | `reject_reason` in accepted values |
| cross-model | conservation (FR-S8); reject rate below a threshold set after profiling (a `warn`, not `error`, so a bad source surfaces without blocking) |
| `gold.news_articles` | `ingest_source` accepted values `['fnspid']`; contract enforced (`contract: enforced: true`) so a column rename breaks the build, not the publish |
| `gold.symbol_daily_news` | `(symbol, trade_date)` unique; counts ≥ 0 |

## 8. Non-functional requirements

- **NFR-1 Memory.** The full build runs on a developer laptop. DuckDB
  `memory_limit` and `threads` are configurable in the dbt profile; spilling to
  a temp directory under `data/` is allowed. No step materialises the dataset in
  pandas.
- **NFR-2 Time.** Target: full `dbt build` over all 15.7M rows in minutes, not
  hours. Record the measured time on the user's machine in the README.
- **NFR-3 Determinism.** Same landing files → byte-identical gold (modulo load
  timestamps). No `ORDER BY` ties left unresolved; no reliance on file read order.
- **NFR-4 Idempotence.** Every layer is full-refresh. Re-running any step is
  always safe.
- **NFR-5 Offline after landing.** FR-L4.
- **NFR-6 Observability.** Row counts per layer and reject counts by reason are
  logged at the end of a run (a dbt `on-run-end` hook or the publish command).
- **NFR-7 Reviewability.** `dbt docs generate` produces a lineage graph; each
  model and column has a description in YAML. This is the portfolio artifact.
- **NFR-8 Isolation.** The DuckDB file is a disposable build artifact. Deleting
  `data/lakehouse/` and re-running must reproduce everything.

## 9. Proposed repo layout

Proposal only — final placement is Q1.

```
Financial_Tools/
├── dbt/fnspid/                      # dbt project (dbt_project.yml, profiles.yml)
│   ├── models/
│   │   ├── bronze/fnspid_news_raw.sql (+ .yml)
│   │   ├── silver/fnspid_articles.sql, fnspid_article_symbols.sql, fnspid_rejects.sql (+ .yml)
│   │   └── gold/news_articles.sql, news_article_securities.sql, symbol_daily_news.sql (+ .yml)
│   ├── seeds/publisher_domains.csv  # FR-E2
│   ├── macros/                      # date parsing, trade_date roll-forward
│   ├── analyses/profile_bronze.sql  # FR-B5
│   └── tests/                       # singular tests (conservation, row count)
├── findata/sources/news/fnspid/
│   ├── download.py                  # FR-L1..L3
│   └── lakehouse.py                 # LakehouseRepository (FR-P2)
├── findata/sources/news/extractors/fnspid_gold.py   # FNSPIDGoldExtractor (FR-P1)
├── tests/fixtures/fnspid/           # tiny CSVs: both header variants + every reject case
├── tests/findata/sources/news/test_fnspid_medallion.py
└── data/                            # git-ignored: raw/fnspid/, lakehouse/fnspid.duckdb
```

`profiles.yml` lives inside the project and reads the DuckDB path from an env
var (e.g. `FNSPID_DUCKDB_PATH`, default `data/lakehouse/fnspid.duckdb`) so it is
committable and contains no secrets.

## 10. Dependencies

| Package | Why | Where pinned |
|---|---|---|
| `duckdb` | engine | `findata/sources/news/requirements.txt` + `uv.lock` |
| `dbt-core`, `dbt-duckdb` | transform framework + adapter | same |
| `huggingface_hub` | landing download (already a transitive dep of `datasets`) | same |

Must be checked before pinning: dbt-core's supported Python versions against
the user's `finance` conda env (discovery 001) and the CI matrix (3.10–3.12).
Pin exact versions; dbt minor releases change behaviour.

## 11. Testing and CI

- **T-1** Fixture CSVs (≤ 50 rows) cover: both header variants, a URL repeated
  across symbols with and without a body, blank URL, each date format plus an
  unparseable one, lower-case symbol, invalid symbol, blank publisher, a
  post-16:00-ET timestamp and a weekend timestamp (FR-E3).
- **T-2** A pytest runs `dbt build` programmatically (`dbtRunner`) over the
  fixtures into a temp DuckDB file and asserts exact expected gold rows. No
  network, no Postgres.
- **T-3** A pytest runs the publish step from that gold into in-memory SQLite
  and asserts `news.articles` / `news.article_securities` contents, then runs it
  again and asserts zero new rows (FR-P3).
- **T-4** CI installs the new deps and runs the above inside the existing
  `python -m pytest` step. No `|| echo` escapes (CLAUDE.md priority #3).

## 12. Acceptance criteria

The work is done when, on the user's machine:

1. `make fnspid-download` lands both CSVs and a manifest; a second run is a no-op.
2. `make fnspid-build` (`dbt build`) passes every test over the full dataset and
   prints per-layer and per-reject-reason counts.
3. Bronze row count = source row count; conservation test passes.
4. `silver.fnspid_articles` has one row per URL, and articles present in the
   nasdaq file carry their body.
5. `make fnspid-publish TICKERS="AAPL MSFT"` loads Postgres; a second run
   inserts nothing; `SELECT count(*) FROM news.article_securities` is ≥ what the
   current extractor path produces for the same filter (REPO_REVIEW #2 fixed).
6. `python -m pytest` passes locally and in CI.
7. `dbt docs generate` renders the lineage graph; README links to it.

## 13. Open questions — the user decides these

| # | Question | Recommendation |
|---|---|---|
| Q1 | Where does the dbt project live: `dbt/fnspid/` at the root, or inside `findata/sources/news/`? | Root `dbt/` — dbt projects aren't Python packages, and one root `dbt/` can later hold market/SEC projects |
| Q2 | Accept dbt `.sql` models as the explicit exception to "no raw SQL outside a repository class"? Needs a line in CLAUDE.md. | Yes — models are the transform layer; Python keeps the rule |
| Q3 | Reject semantics: is a row with a bad symbol but good URL/date an article (with no link) or a full reject? | Keep the article, reject only the link |
| Q4 | Canonicalise URLs beyond scheme/host (strip `utm_*`, trailing `/`)? | Not in MVP — it changes the dedup key relative to rows already in Postgres |
| Q5 | Publish enrichment columns to Postgres (`trade_date`, `url_domain`, `sentiment_text`, …)? That needs a model change + migration. | Not in MVP. Keep them in gold; revisit when the demo needs them |
| Q6 | Keep the four FNSPID summary columns (`Lsa_summary` …) past silver? | Keep in silver, drop from gold unless profiling shows they're populated and useful |
| Q7 | Trading-calendar source for FR-E3: weekday-only approximation, a seeded NYSE holiday list, or read-only attach of Postgres `market.daily_bars`? | Seeded holiday list for MVP (offline, deterministic); `daily_bars` attach is the stretch (FR-E6/E7) |
| Q8 | How long does the old HF `datasets` path stay around? | It stops being the entry point as soon as publish lands (FR-P6), and the code is removed after acceptance criterion 5 (FR-P8). No period where two FNSPID loaders are both live |
| Q9 | Scale of publish: all 15.7M rows through ORM batches, or a bulk path (Postgres `COPY` inside `ArticleRepository`)? | ORM batches for MVP with ticker/date filters; bulk path is a follow-up if a full publish is too slow |
| Q10 | Disk budget: is there room for the raw CSVs plus the DuckDB file (roughly 2–3× the CSV size), or should bronze read over `hf://` instead? | Land locally (§5.1). Measure the file sizes in PR 1 and switch to `hf://` only if disk is the blocker |

## 14. Delivery plan (each ≈ one PR)

1. **Landing + bronze + profiling.** Download command, bronze model, FR-B5
   profile, discovery note with the profile results. Answers Q3/Q6 with data.
2. **Silver.** Articles, symbols, rejects, conservation test, fixture-driven pytest.
3. **Gold + MVP enrichment.** FR-G*, FR-E1–E5, contracts.
4. **Publish + cut-over.** `LakehouseRepository`, `FNSPIDGoldExtractor`,
   `--fnspid` / Make targets switched to gold (FR-P6), T-3, README "how to
   run" + lineage screenshot.
5. **Retire + stretch.** Remove the HF `datasets` path (FR-P8); warehouse
   attach for FR-E6/E7.

Docs to update as part of these PRs (not done in this one): `REPO_MAP.md`
(new paths and entry points), `CLAUDE.md` router table (a row pointing here) and
non-negotiables (Q2), `RECIPES.md` ("add a dbt model"), `.gitignore` (`data/`),
the news `README.md` source table, and discovery 006's `streaming=True` claim,
which no longer matches the code.
