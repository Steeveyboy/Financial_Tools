# News Articles ETL

Ingests financial news articles from multiple sources into a shared database for downstream analysis — sentiment scoring, entity extraction, and correlation with market price data.

Part of the [Resonance Desk](../README.md) data warehouse.

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
news_articles/
  config.py               # DATABASE_URL and environment variable loading
  pipeline.py             # ExtractionPipeline, TransformationPipeline
  db/
    schema.py             # SQLAlchemy table definitions (articles, article_tickers)
    repository.py         # All database reads and writes
  extractors/
    base.py               # ArticleExtractor abstract base class
    rss.py                # RSS/Atom feed extractor (Reuters Business)
    huggingface.py        # HuggingFace dataset extractor (FNSPID)
  transformers/
    base.py               # ArticleTransformer abstract base class
    sentiment.py          # Sentiment scoring stub
    entity.py             # Ticker entity extraction stub
  requirements.txt
```

### Database tables

**`articles`** — one row per unique article, keyed by URL

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | Auto-increment primary key |
| `url` | TEXT | Unique — used for deduplication |
| `title` | TEXT | Headline |
| `author` | TEXT | Byline (nullable) |
| `publisher` | TEXT | Outlet name, e.g. "Reuters" |
| `source` | TEXT | Extractor identifier, e.g. "rss" |
| `content` | TEXT | Plain text body (nullable) |
| `published_at` | DATETIME | Publication timestamp (UTC) |
| `fetched_at` | DATETIME | Row insert timestamp (set by DB) |

**`article_tickers`** — links articles to the companies they mention

| Column | Type | Notes |
|---|---|---|
| `article_id` | INTEGER | Foreign key → articles.id |
| `ticker` | TEXT | e.g. "AAPL" |

---

## Setup

**1. Install dependencies**

```bash
pip install -r news_articles/requirements.txt
```

**2. Set the database URL**

```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/resonance"
# or for local development:
export DATABASE_URL="sqlite:///resonance.db"
```

Add this to a `.env` file in the project root to avoid setting it every session.

---

## Running the pipeline

Run from the project root (`Financial_Tools/`).

**Phase 1 — Extract and load articles**

```python
from sqlalchemy import create_engine
from news_articles.pipeline import ExtractionPipeline
from news_articles.extractors.rss import RSSExtractor
from news_articles.extractors.huggingface import FNSPIDExtractor

engine = create_engine("sqlite:///resonance.db")

ExtractionPipeline(engine, extractors=[
    # Reuters Business RSS feed (fetches latest articles)
    RSSExtractor(),

    # FNSPID historical dataset — filter by ticker and date to avoid
    # streaming all 15.7 million rows
    FNSPIDExtractor(
        tickers=["AAPL", "MSFT", "NVDA"],
        start_date="2020-01-01",
        end_date="2023-12-31",
    ),
]).run()
```

**Phase 2 — Apply transforms** *(once transformers are implemented)*

```python
from news_articles.pipeline import TransformationPipeline
from news_articles.transformers.sentiment import SentimentTransformer
from news_articles.transformers.entity import EntityTransformer

TransformationPipeline(engine, transformers=[
    SentimentTransformer(),
    EntityTransformer(),
]).run()

# Re-run a single transform by name
TransformationPipeline(engine, transformers=[SentimentTransformer()]).run("sentiment")
```

---

## Adding a new source

Create a new file in `extractors/` that subclasses `ArticleExtractor`:

```python
# extractors/my_source.py
from .base import ArticleExtractor

class MySourceExtractor(ArticleExtractor):
    source_id = "my_source"   # stored in articles.source column

    def extract(self) -> list[dict]:
        # Fetch articles from your source here.
        # Return a list of dicts with these fields:
        return [
            {
                "url":          "https://...",   # required — used for dedup
                "title":        "Headline",
                "author":       "Jane Smith",     # optional
                "publisher":    "My Outlet",      # optional
                "content":      "Article body...", # optional, plain text only
                "published_at": datetime(...),    # optional
            }
        ]
```

Then register it in the pipeline:

```python
ExtractionPipeline(engine, extractors=[
    RSSExtractor(),
    MySourceExtractor(),
]).run()
```

That's it. The pipeline handles deduplication, source tagging, and database insertion automatically.

If your source already knows which tickers an article is about, include a `mentioned_tickers` field (list of strings) in each dict — the pipeline will link them to the `article_tickers` table at load time without needing to run the `EntityTransformer`.

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
