# 007 — dojo_stock_news `symbol` is the scraped-from page, not an article symbol

- **Verified against:** commit `bd5cf8f` on 2026-10-04 (first 50,000 rows of
  `AlphaDojo/dojo_stock_news`, streamed)
- **Applies to:** `findata/models/dojo_stock_news.py`,
  `findata/sources/news/staging/dojo.py`, any future dojo → `news.articles` transform

## What I found

The dataset README calls `symbol` the "associated stock symbol (primary query
key)". It isn't associated with the article in any useful sense. In the sample:

| Check | Rows (of 50,000) |
|---|---|
| `symbol` equals `primarysymbol` | 4 |
| `symbol` appears in `on_symbol_json` | 7 |
| `primarysymbol` appears in `on_symbol_json` | 47,470 |
| `on_symbol_json` empty | 0 |

The 50,000 rows held only **79 distinct URLs**, one repeated 641 times. Each
article is repeated once per stock page it was listed on, and `symbol` names that
page: ETFs (`TAN`, `EWT`), `BTC`, OTC tickers (`PINWF`). A Motley Fool article
about EPD, for example, arrived with `symbol = "NVVE"`.

The article's own symbols are in `on_symbol_json`, a JSON list of
`{"symbol": "EPD", "type": "stocks"}` (uppercase). `primarysymbol` is the
lowercase lead symbol and is usually one of those.

Smaller details: `source` comes through as `None`; `publish_date` is free text
such as `"Oct 3, 2026"`.

### The dataset is two populations (full parquet scan, 2026-10-04)

`data.parquet` holds **3,975,040 rows**, not the ~2.52M its README claims:

| Rows | `source` | Looks like |
|---|---|---|
| 0 – 2,285,984 | `None` | English, Nasdaq-style; the sample above |
| 2,285,985 – end | `eastmoney` (1,689,055 rows) | Chinese titles, empty `description`, ISO `publish_date` (`2026-10-04T08:49:28+00:00`), symbols like `601398.SS` / `1398.HK` |

The source `id` is `float64`. Eastmoney ids reach ~2×10²², above Postgres
`bigint` (304,784 rows overflow), and are already rounded by the float. In one
case the id read `…549728` while the URL said `…549738`. The id is therefore
**not stored**; `url` is the article key.

## Why it bites

Linking articles by `symbol` would attach almost every article to the wrong
securities, many times over, since each article repeats once per page. Using `symbol` as a ticker would also break the schema's
"one `symbol` column, one width" rule (`test_symbol_columns_agree_on_width`).

## What to do

- The staging table stores it as **`page_symbol`**, so `symbol` keeps meaning
  "joinable ticker" across the warehouse.
- `DojoExtractor` (`findata/sources/news/extractors/dojo.py`) normalizes the
  table into `news.articles`, one article per `url`. For English rows it links
  `on_symbol_json` and ignores `page_symbol`. **Eastmoney rows are the
  exception:** they have no `on_symbol_json`, and their `page_symbol` values do
  look relevant (a bank article listed under four bank tickers), so every
  `page_symbol` of the URL is linked. Spot-checked only; treat eastmoney links
  as lower precision.
