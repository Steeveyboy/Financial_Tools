# findata.sources.news — News ETL

Ingests financial news articles from multiple sources into the `articles` /
`article_tickers` tables of the findata warehouse for downstream analysis —
sentiment scoring, entity extraction, and correlation with market price data.

Part of the [Resonance Desk](../../../README.md) data warehouse.

---

## Architecture

The pipeline is split into two independent phases:

```
Phase 1 — Extraction (run on a schedule)
  Extractor A ──┐
  Extractor B ──┼──► ArticleRepository.insert_articles() ──► articles table
  Extractor N ──┘                                         ──► article_tickers table

Phase 2 — Transformation (run separately, can be re-run at any time)
  articles table ──► SentimentTransformer  ──► sentiment_score column
                 ──► EntityTransformer     ──► article_tickers table
```

Keeping extraction and transformation separate means:
- New transforms can be applied retroactively to the full historical dataset
- Extraction can run frequently without triggering expensive model inference
- Each transform can be re-run independently if the model is improved

### Module layout

```
findata/
  models/
    article.py             # Article ORM model (defines the articles table)
    article_ticker.py      # ArticleTicker ORM model (composite PK)
  sources/
    news/
      config.py            # DATABASE_URL and environment variable loading
      pipeline.py          # ExtractionPipeline, TransformationPipeline
      db/
        repository.py      # ArticleRepository — all DB reads and writes
      extractors/
        base.py            # ArticleExtractor abstract base class
        rss.py             # RSS/Atom feed extractor (Reuters Business)
        huggingface.py     # HuggingFace dataset extractor (FNSPID)
      transformers/
        base.py            # ArticleTransformer abstract base class
        sentiment.py       # Sentiment scoring stub
        entity.py          # Ticker entity extraction stub
      requirements.txt
```

Schema definitions live in `findata.models`; the news source only contains
extraction/transform logic and the repository that wraps the underlying
ORM models. Migrations live in the single Alembic tree at
`findata/db/migrations/`.

### Database tables

**`articles`** — one row per unique article, keyed by URL

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | Auto-increment primary key |
| `url` | TEXT | Unique — used for deduplication |
| `title` | TEXT | Headline |
| `author` | TEXT | Byline (nullable) |
| `publisher` | VARCHAR(255) | Outlet name, e.g. "Reuters" |
| `source` | VARCHAR(64) | Extractor identifier, e.g. "rss" |
| `content` | TEXT | Plain text body (nullable) |
| `published_at` | DATETIME | Publication timestamp |
| `fetched_at` | DATETIME | Row insert timestamp (server default `now()`) |

**`article_tickers`** — links articles to the companies they mention

| Column | Type | Notes |
|---|---|---|
| `article_id` | INTEGER | FK → `articles.id` (`ON DELETE CASCADE`); part of PK |
| `ticker` | VARCHAR(10) | e.g. "AAPL"; part of PK |

The composite primary key `(article_id, ticker)` means the same pair can only
be linked once. Inserts use `INSERT ... ON CONFLICT DO NOTHING` so transforms
can be safely re-run without raising `IntegrityError`.

---

## Setup

**1. Install dependencies**

```bash
pip install -r findata/sources/news/requirements.txt
```

**2. Set the database URL**

```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/resonance"
# or for local development:
export DATABASE_URL="sqlite:///resonance.db"
```

Add this to a `.env` file at the project root to avoid setting it every session.

---

## Running the pipeline

Run from the project root (`Financial_Tools/`).

The convenience script `load_news_articles.py` wires up the RSS and FNSPID
extractors and runs `ExtractionPipeline`:

```bash
python load_news_articles.py                     # RSS only (default)
python load_news_articles.py --fnspid \
    --tickers AAPL MSFT NVDA \
    --start-date 2020-01-01 --end-date 2023-12-31
```

To drive the pipeline directly from Python:

**Phase 1 — Extract and load articles**

```python
from findata.sources.news.pipeline import ExtractionPipeline
from findata.sources.news.extractors.rss import RSSExtractor
from findata.sources.news.extractors.huggingface import FNSPIDExtractor

# ExtractionPipeline accepts an explicit engine or falls back to
# findata.db.session.get_engine() (which reads DATABASE_URL).
ExtractionPipeline(engine=None, extractors=[
    RSSExtractor(),
    FNSPIDExtractor(
        tickers=["AAPL", "MSFT", "NVDA"],
        start_date="2020-01-01",
        end_date="2023-12-31",
    ),
]).run()
```

**Phase 2 — Apply transforms** *(once transformers are implemented)*

```python
from findata.sources.news.pipeline import TransformationPipeline
from findata.sources.news.transformers.sentiment import SentimentTransformer
from findata.sources.news.transformers.entity import EntityTransformer

TransformationPipeline(engine=None, transformers=[
    SentimentTransformer(),
    EntityTransformer(),
]).run()

# Re-run a single transform by name
TransformationPipeline(engine=None, transformers=[SentimentTransformer()]).run("sentiment")
```

---

## Adding a new source

Create a new file in `extractors/` that subclasses `ArticleExtractor`:

```python
# findata/sources/news/extractors/my_source.py
from .base import ArticleExtractor

class MySourceExtractor(ArticleExtractor):
    source_id = "my_source"   # stored in articles.source column

    def extract(self) -> list[dict]:
        # Fetch articles from your source here.
        return [
            {
                "url":          "https://...",      # required — used for dedup
                "title":        "Headline",
                "author":       "Jane Smith",        # optional
                "publisher":    "My Outlet",         # optional
                "content":      "Article body...",   # optional, plain text only
                "published_at": datetime(...),       # required
            }
        ]
```

Then register it in the pipeline:

```python
ExtractionPipeline(engine=None, extractors=[
    RSSExtractor(),
    MySourceExtractor(),
]).run()
```

If your source already knows which tickers an article is about, include a
`mentioned_tickers` field (list of strings) in each dict — the pipeline will
link them to the `article_tickers` table at load time without needing to run
the `EntityTransformer`.

```python
{
    "url":               "https://...",
    "title":             "Apple reports record earnings",
    "mentioned_tickers": ["AAPL"],   # linked immediately on insert
    ...
}
```

---

## Current data sources

| Source | Extractor | Coverage | Full text |
|---|---|---|---|
| Reuters Business RSS | `RSSExtractor` | Live feed | Summary only |
| FNSPID (HuggingFace) | `FNSPIDExtractor` | 1999–2023, 15.7M articles | Title only |

## Planned transforms

| Transform | Status | Notes |
|---|---|---|
| Sentiment scoring | Stub | See `transformers/sentiment.py` for implementation options |
| Ticker entity extraction | Stub | Not needed for FNSPID (tickers provided directly) |
