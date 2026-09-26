# Data Model & Naming Standard

The authoritative description of the `resonance_desk` warehouse: the naming rules
every object obeys, the schema layout, and the reasoning behind the structural
choices.

`findata/models/` is the implementation. If the two disagree, **the models win**
and this document is wrong — fix it. `tests/findata/models/test_naming_convention.py`
enforces the rules in section 1 mechanically, so a new model that ignores them
fails the suite rather than quietly drifting.

Companion documents: [`REPO_MAP.md`](REPO_MAP.md) for navigation,
[`CLEANUP_PLAN.md`](CLEANUP_PLAN.md) for the package consolidation and the
deferred security master (Phase 8),
[`SENTIMENT_TRANSFORM.md`](SENTIMENT_TRANSFORM.md) for the FinBERT transform.

---

## 1. Naming rules

### Database

One database: **`resonance_desk`**.

```
postgresql+psycopg2://user:pass@localhost:5432/resonance_desk
```

The old name `corporate_db` described one domain of several and is retired.

### Schemas

Tables are grouped by domain into Postgres schemas mirroring `findata/sources/`.
Nothing lives in `public` except `alembic_version`.

| Schema | Holds | Change rate |
|---|---|---|
| `reference` | Exchanges, issuers, insiders | Slowly-changing |
| `market` | Price and volume time series | Append-mostly, high volume |
| `news` | Articles, symbol links, transform bookkeeping | Append-mostly, high volume |

`reference` is the industry term for this class of data ("ref data"), and the
split is the one a reader already expects: dimensions in one place, facts in
another.

**SQLite has no schemas.** `findata.db.base.schema_translate_map_for()` returns a
map collapsing all three to the default schema, applied automatically by
`findata.db.session.get_engine()`, by `ArticleRepository` for an injected engine,
and by Alembic's `env.py`. Table names do not collide across schemas, so the
collapse is lossless — that is a constraint on future table names, not an
accident.

`alembic_version` stays in the default schema. A `meta` schema was considered and
dropped: it would have held that one table, and moving Alembic's bookkeeping off
the default schema buys nothing but a configuration flag that can only break.

### Tables

- `snake_case`, always **plural**: `companies`, `daily_bars`, `articles`.
- Named for what a row *is*, never for the source that produced it or the process
  that writes it.
- Link tables are `<left>_<right>`, both plural: `article_securities`.
- No schema prefix in the table name — the schema already says it.
  `market.daily_bars`, not `market.market_daily_bars`.

### Columns

| Rule | Example | Not |
|---|---|---|
| `snake_case`, lowercase | `adj_close` | `adjClose` |
| `*_id` is an integer surrogate key or an FK to one — **never** free text | `article_id` | `transform_id` holding `"sentiment"` |
| `*_at` is a timestamp instant, always `timestamptz` | `published_at` | `published_date` |
| `*_date` is a calendar date with no time | `trade_date` | `date` |
| `is_*` is a non-null boolean with a server default | `is_active` | `active` |
| No table-name prefix on columns | `companies.name` | `companies.company_name` |
| Spell out the domain term | `symbol` | `tkr`, `sym` |

Three deliberate exceptions, each enforced as an exception in the test rather
than left to memory:

- **`open` / `high` / `low` / `close`** collide with SQL keywords and are quoted
  by SQLAlchemy. They stay, because every consumer of a bar table expects exactly
  these four names and inventing `open_price` would be worse.
- **External identifiers** keep the name the outside world uses even when it ends
  in `_id` — `sedar_id` is SEDAR+'s own term. Renaming a standard identifier to
  satisfy an internal rule loses more than it gains.
- **`transformed_at`** doubles as `article_transforms`' write timestamp, so that
  table has no `created_at` / `updated_at` pair.

### `symbol`, not `ticker`

One term for a traded symbol across the whole warehouse: **`symbol`**,
`String(32)`, uppercase-enforced by a `CHECK` constraint on every table that has
one.

`String(32)` covers share-class and venue suffixes (`BRK.B`, `RY.TO`) with room
left. The previous schema had `companies.ticker String(20)` alongside
`article_tickers.ticker String(10)` and `daily_ohlcv.ticker String(10)`, so a
symbol that inserted into one table was silently rejected by the next.

The uppercase constraint matters more than it looks. Symbols are the join key
between tables populated by *different pipelines* — the news extractor and the
price fetcher have no contact with each other. One emitting `aapl` and the other
`AAPL` produces **zero rows and no error**. The constraint makes that
impossible to store rather than something to remember.

### Audit columns

**Every** table carries exactly these two (see `findata/models/mixins.py`):

```python
created_at: timestamptz NOT NULL  server_default=now()
updated_at: timestamptz NOT NULL  server_default=now()  onupdate=now()
```

They mean "when this warehouse row was written / last changed" — never anything
about the underlying event. Event time is a named domain column (`published_at`,
`trade_date`). The old `fetched_at` columns collapsed into `created_at`: they
meant the same thing under a name that only existed on the two tables whose
author happened to think of it.

Both defaults are server-side, so the database clock is authoritative and rows
written by bulk INSERT — which bypasses Python-side defaults — still get values.

### Constraints and indexes

Names are generated, not hand-written. `findata/db/base.py` sets a
`MetaData(naming_convention=...)`:

| Kind | Template | Example |
|---|---|---|
| Primary key | `pk_%(table_name)s` | `pk_daily_bars` |
| Foreign key | `fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s` | `fk_companies_exchange_id_exchanges` |
| Unique | `uq_%(table_name)s_%(column_0_N_name)s` | `uq_companies_symbol_exchange_id` |
| Index | `ix_%(table_name)s_%(column_0_N_name)s` | `ix_daily_bars_trade_date` |
| Check | `ck_%(table_name)s_%(constraint_name)s` | `ck_daily_bars_high_ge_low` |

This is the single highest-value change in the rebuild. Previously `Base` was a
bare `DeclarativeBase` with no convention, so **every primary key, foreign key
and check constraint carried a name the server invented** — different between
Postgres and SQLite, and impossible to reference in a migration that wants to
drop or alter one. The three index names that did exist used three different
conventions (`ix_company_ticker`, `ix_articles_published_at`,
`ix_article_tickers_ticker_article`).

Because `ck` interpolates `%(constraint_name)s`, every `CheckConstraint` must be
given a short explicit name (`name="high_ge_low"`), which the convention then
expands. SQLAlchemy raises if one is omitted.

Postgres truncates identifiers at 63 characters, so keep composite index column
counts low; the test asserts the limit.

---

## 2. Schema

### `reference.exchanges`

Trading venues. Small and hand-seeded — see `findata.db.session._seed_exchanges`
(NYSE, NASDAQ, TSX, TSXV).

| Column | Type | Notes |
|---|---|---|
| `id` | `int` PK | |
| `code` | `varchar(20)` UNIQUE NOT NULL | `NYSE`, `TSX` — the natural key |
| `name` | `varchar(100)` NOT NULL | |
| `country` | `varchar(100)` | |
| `currency` | `varchar(10)` | Venue's trading currency |
| `timezone` | `varchar(50)` | IANA name, e.g. `America/New_York` |

### `reference.companies`

A listed issuer.

| Column | Type | Notes |
|---|---|---|
| `id` | `int` PK | |
| `name` | `varchar(255)` NOT NULL | |
| `symbol` | `varchar(32)` NOT NULL | Was `ticker String(20)` |
| `exchange_id` | `int` FK → `exchanges.id` NOT NULL | `ON DELETE RESTRICT` |
| `country`, `sector`, `industry` | `varchar` | Each indexed |
| `description` | `text` | Full-text indexed — see below |
| `website`, `headquarters` | `varchar(255)` | |
| `market_cap` | `bigint` | **Point-in-time snapshot, not a series** — overwritten on refresh |
| `employees` | `int` | |
| `fiscal_year_end` | `varchar(10)` | |
| `isin`, `cusip`, `cik`, `sedar_id` | `varchar` | External identifiers; `cik` is the Phase 6 SEC join key |
| `is_active` | `bool` NOT NULL | |

- `UNIQUE (symbol, exchange_id)`, `CHECK (symbol = upper(symbol))`

`symbol` and `exchange_id` are really attributes of a *security*, not an issuer —
an issuer with two share classes has two symbols. Phase 8 of
[`CLEANUP_PLAN.md`](CLEANUP_PLAN.md) moves them onto a `reference.securities`
table; until a source exists that can populate a security master, they stay here.

`description` carries a dialect-conditional full-text index: a Postgres GIN index
`ix_companies_description_fts`, or a SQLite FTS5 virtual table `companies_fts`.
Both are created by `after_create` event listeners in `models/company.py`, **not**
declared on the model, so Alembic autogenerate cannot see them and reports them
as "removed". Both names are listed in `env.py`'s `_EVENT_CREATED_OBJECTS` to
suppress the `DROP` that would otherwise destroy the search index. **Any future
event-listener DDL must be added there too**, along with any shadow-table prefix.

### `reference.insiders`

| Column | Type | Notes |
|---|---|---|
| `id` | `int` PK | |
| `company_id` | `int` FK → `companies.id` NOT NULL | `ON DELETE CASCADE`, indexed |
| `full_name` | `varchar(255)` NOT NULL | Was `name` — ambiguous next to `companies.name` in a join |
| `role` | `varchar(100)` | |
| `is_board_member`, `is_insider` | `bool` NOT NULL | |
| `start_date`, `end_date` | `date` | |

### `market.daily_bars`

Daily OHLCV. Renamed from `daily_ohlcv` — plural, and `bars` generalizes to the
`intraday_bars` this will sit next to.

| Column | Type | Notes |
|---|---|---|
| `symbol` | `varchar(32)` | PK part |
| `trade_date` | `date` | PK part. Was `date`, which shadowed the Python builtin |
| `open`, `high`, `low`, `close` | `numeric(18,6)` | **As-traded, unadjusted** |
| `adj_close` | `numeric(18,6)` | **Split- and dividend-adjusted — use this for returns** |
| `volume` | `bigint` | |
| `dividend_amount` | `numeric(18,6)` NOT NULL default 0 | Cash distribution with ex-date on `trade_date` |
| `split_coefficient` | `numeric(18,6)` NOT NULL default 1 | Ratio effective `trade_date`; a 4:1 split is 4 |
| `source` | `varchar(32)` NOT NULL | Provider that supplied the bar |

- `PRIMARY KEY (symbol, trade_date)`
- `INDEX (trade_date)` — cross-sectional queries ("every bar on 2026-03-14")
- `CHECK high >= low`, `CHECK volume >= 0`, `CHECK split_coefficient > 0`,
  `CHECK symbol = upper(symbol)`

**`adj_close` is new and it mattered.** The previous table had only raw OHLC, so
no correct return could be computed from it: a 4:1 split shows up as a −75%
one-day return and dividends vanish. Worse, the loader passed
`auto_adjust=True` to yfinance, which returns an *already-adjusted* `Close` and
no `Adj Close` at all — so the column named `close` held adjusted prices and the
raw price was nowhere. The loader now passes `auto_adjust=False, actions=True`
and stores both, plus the dividend and split data, so the adjustment can be
recomputed rather than trusted.

Prices use `numeric(18,6)` rather than `(12,4)`: adjusted closes of long
histories get very small, and adjustment factors carry more precision than a
traded price does.

The `CHECK` constraints are cheap and catch provider glitches at write time
instead of in a backtest. `NULL` columns make them evaluate to unknown, which
passes — partial bars are still allowed.

### `news.articles`

| Column | Type | Notes |
|---|---|---|
| `id` | `int` PK | |
| `url` | `text` UNIQUE NOT NULL | The deduplication key for the whole pipeline |
| `title`, `author`, `content` | `text` | |
| `publisher` | `varchar(255)` | **Who published it** — Reuters, Bloomberg |
| `ingest_source` | `varchar(32)` NOT NULL | **Which extractor produced the row** — `rss`, `fnspid` |
| `published_at` | `timestamptz` NOT NULL | Indexed |
| `sentiment_score` | `float` | Signed `[-1, 1]`; see `SENTIMENT_TRANSFORM.md` |

`publisher` and `ingest_source` were previously `publisher` and `source`, a pair
of names that gave no clue which was which.

`published_at` stays `NOT NULL`: an article with no timestamp cannot enter a time
series, so it is not worth a row. Extractors *do* emit `None` for malformed feed
entries, so `ArticleRepository.insert_articles()` filters and counts them rather
than letting one bad entry fail the whole batch with an `IntegrityError`. That is
REPO_REVIEW #4.

### `news.article_securities`

Which symbols an article mentions. Renamed from `article_tickers`.

| Column | Type | Notes |
|---|---|---|
| `article_id` | `int` FK → `articles.id` | PK part, `ON DELETE CASCADE` |
| `symbol` | `varchar(32)` | PK part, uppercase-enforced |
| `link_source` | `varchar(32)` NOT NULL | `extractor` or `entity_transform` |

- `PRIMARY KEY (article_id, symbol)` — makes re-running extraction idempotent via
  dialect-aware `INSERT … ON CONFLICT DO NOTHING`
- `INDEX (symbol, article_id)` — "every article mentioning X", the query the demo
  runs most

`link_source` records provenance because the two paths have very different
precision: a symbol the feed asserted is far more reliable than one inferred from
article text by the entity transform. Without the column, a model trained on
these links cannot tell them apart.

Phase 8 adds a nullable `security_id` FK beside `symbol` and keeps `symbol` in the
key, so an unresolvable mention is still recorded and can be resolved in place
later.

### `news.article_transforms`

One row per (article, transform) application. Renamed from `transform_log`:
plural, and "log" named the mechanism rather than the contents.

| Column | Type | Notes |
|---|---|---|
| `article_id` | `int` FK → `articles.id` | PK part, `ON DELETE CASCADE` |
| `transform_name` | `varchar(64)` | PK part. `sentiment`, `entity_extraction` |
| `transformed_at` | `timestamptz` NOT NULL | |

- `PRIMARY KEY (article_id, transform_name)`
- `INDEX (transform_name, article_id)` — the anti-join path in
  `get_untransformed()`; leading with `transform_name` is what makes it seek
  rather than scan

`transform_id` became `transform_name` because it held a string like
`"sentiment"`, violating the `*_id`-is-an-integer rule. The repository's Python
parameter was already called `transform_name`, so this also removes a
long-standing mismatch between argument and column. The same rename applied to
the `ArticleTransformer.transform_id` class attribute and
`ArticleExtractor.source_id` (now `ingest_source`, named for the column it fills).

A row records the **attempt**, not the result, which is what lets a `NULL`
`sentiment_score` mean two different things safely. See
[`SENTIMENT_TRANSFORM.md`](SENTIMENT_TRANSFORM.md).

---

## 3. Timestamps are all `timestamptz`

Every `*_at` column uses `findata.db.types.UTCDateTime`, a `TypeDecorator` over
`DateTime(timezone=True)`. Previously the reference tables were tz-aware and the
news and market tables were naive, which is the direct cause of REPO_REVIEW #3
(FNSPID date filtering crashing on an aware-vs-naive comparison: `_parse_date()`
returned aware, `start_date`/`end_date` came from a bare `strptime()` and were
naive).

The decorator does two things:

- **On write**, `ensure_utc()` normalizes whatever it is given. A naive value is
  *assumed UTC* and stamped; an aware one is converted. The assumption is
  recorded in one place rather than repeated at each call site.
- **On read**, a naive value is stamped UTC. This matters because Postgres
  `timestamptz` round-trips awareness natively and **SQLite does not** — the same
  logical row would come back aware in production and naive in tests, and
  comparing the two raises `TypeError`.

DDL is unchanged: `alembic check` and migrations see an ordinary `timestamptz`.

A naive timestamp on market data is not a style question — it makes a bar
ambiguous across a DST boundary.

---

## 4. Migration history

The rebuild squashes migrations `0001`–`0004` into a single `0001_baseline.py`
describing the final schema. The database is recreated from empty, so no rename
or `ALTER` steps are needed, and a reader sees one coherent schema definition
instead of four incremental patches plus renames reversing earlier decisions.

`0001_baseline.py` issues `CREATE SCHEMA IF NOT EXISTS` for the three schemas
before creating tables, and skips that on SQLite.

The three known drift items from the old Postgres database
(`ix_article_tickers_ticker_pub` naming, nullable `articles.published_at`,
missing `daily_ohlcv.fetched_at`) are **resolved by the rebuild rather than
repaired** — none of those objects survives into the new schema.

`alembic upgrade head` is the only schema path. `init_db()` /
`Base.metadata.create_all()` remains for tests and throwaway SQLite only; it is
what caused the original divergence.

### `alembic check` only works against Postgres

The models declare schemas; SQLite has none, so the engine applies a
`schema_translate_map`. That map governs *SQL execution*, not metadata
comparison — autogenerate diffs `Base.metadata` (`schema='news'`) against SQLite
reflection (`schema=None`) and reports **every table as both added and removed**.
The output is noise, not drift.

`tests/findata/db/test_migration_matches_models.py` is the SQLite-side
equivalent: it builds one database with `alembic upgrade head` and another with
`create_all()`, then compares object sets and per-table clause sets
(order-independent, since the two paths emit constraints in different orders).
It also inserts a row, because some DDL differences only fail on write.

That test caught the baseline using `sa.text("now()")` for timestamp defaults,
which is emitted verbatim — SQLite would have got `DEFAULT (now())`, a function
it does not have, and every INSERT would have failed. **Use `sa.func.now()` in
migrations**, which compiles per dialect.

---

## 5. Rebuilding the database

These commands drop and recreate the database. **Run them yourself** — nothing in
this repo executes DDL against your Postgres.

```bash
# 1. Back up the old database. It is a different database, so this is insurance,
#    not a dependency:
pg_dump -Fc corporate_db > ~/corporate_db.$(date +%F).dump

# 2. Create the new one:
createdb resonance_desk

# 3. Point the repo at it — set DATABASE_URL to
#    postgresql+psycopg2://USER@localhost:5432/resonance_desk
$EDITOR .env

# 4. Build the schema:
alembic upgrade head

# 5. Confirm models and database agree (Postgres only — see section 4):
alembic check

# 6. Load reference data first, then facts:
python -m descriptions.populate_db
python -m findata.sources.market.fetch_stock_data findata/sources/market/tickers.json
python load_news_articles.py
python transform_news.py
```

Keep `corporate_db` until `resonance_desk` is populated and verified, then drop
it.

### Verification

```sql
-- every table, with row counts
SELECT schemaname, relname, n_live_tup
FROM pg_stat_user_tables ORDER BY schemaname, relname;

-- constraint names should all match section 1's convention
SELECT conrelid::regclass AS tbl, conname, contype
FROM pg_constraint
WHERE connamespace::regnamespace::text IN ('reference','market','news')
ORDER BY 1, 2;

-- adjusted vs raw close: should differ only where splits/dividends occurred
SELECT symbol, trade_date, close, adj_close, dividend_amount, split_coefficient
FROM market.daily_bars
WHERE close <> adj_close
ORDER BY trade_date DESC LIMIT 20;

-- sentiment coverage: scored vs no-usable-text vs pending
SELECT
  count(*) FILTER (WHERE t.article_id IS NOT NULL AND a.sentiment_score IS NOT NULL) AS scored,
  count(*) FILTER (WHERE t.article_id IS NOT NULL AND a.sentiment_score IS NULL)     AS no_text,
  count(*) FILTER (WHERE t.article_id IS NULL)                                       AS pending
FROM news.articles a
LEFT JOIN news.article_transforms t
  ON t.article_id = a.id AND t.transform_name = 'sentiment';

-- symbols mentioned in news that have no price history: the join-coverage metric
SELECT DISTINCT s.symbol
FROM news.article_securities s
LEFT JOIN market.daily_bars b ON b.symbol = s.symbol
WHERE b.symbol IS NULL
ORDER BY 1 LIMIT 50;
```

That last query is the one to watch. It measures whether the news and market
pipelines actually agree on symbols — the thing the whole warehouse depends on,
and the thing Phase 8's security master exists to make structural.

---

## 6. Known gaps

Honest list, so a reader does not have to find these by reading the models.

| Gap | Consequence |
|---|---|
| Symbol is the join key, with no security master | A renamed symbol (`FB` → `META`) splits one company's history in two, and a reissued symbol splices two companies together. Deferred deliberately — see Phase 8 in [`CLEANUP_PLAN.md`](CLEANUP_PLAN.md) |
| `companies.market_cap` is a snapshot on a dimension table | Overwritten on each refresh; no history. Belongs in a `reference.company_fundamentals` series |
| No corporate-actions table | `dividend_amount` / `split_coefficient` ride on the bar, which is enough to recompute an adjustment but is not a queryable action history |
| `daily_bars.adj_close` is provider-supplied | Adjustment methodology is yfinance's, not recomputed from the stored dividend/split columns |
| No point-in-time guarantees | Reference rows are updated in place, so a backtest cannot reconstruct what was known on a past date. Real bitemporal versioning is a much larger change |
| `daily_bars.symbol` has no FK | Nothing stops a bar for a symbol no `companies` row knows about. Intentional for now: price history usually arrives before issuer data |
