"""
transformers/entity.py

Entity extraction transformer stub.

Identifies company/ticker mentions in article content and populates the
news.article_securities association table. This is what enables the query:
"give me all articles mentioning AAPL, ordered by date".

Once this transformer runs, ArticleRepository.get_by_ticker() becomes useful.

Approaches:
    Option A — Dictionary lookup (fast, lower recall)
        Build a lookup from company names → ticker symbols using the tickers.json
        file already in the repo (findata/sources/market/tickers.json). Search article text
        for company names or ticker symbols. Simple but misses paraphrases.

    Option B — spaCy NER (recommended for accuracy)
        Use spaCy's named entity recognition to extract ORG entities, then
        map them to tickers using a fuzzy match against known company names.
        `pip install spacy && python -m spacy download en_core_web_sm`

    Option C — LLM extraction
        Prompt the Claude API to return a JSON list of tickers mentioned.
        Most accurate, handles nicknames and indirect references ("the iPhone maker").

To implement:
    1. Choose an approach above
    2. Add required dependencies to requirements.txt
    3. Fill in `transform()` — populate article["mentioned_symbols"] list
    4. The pipeline will call repo.link_symbols() with those results
"""

from __future__ import annotations

import logging

from .base import ArticleTransformer

_logger = logging.getLogger(__name__)


class EntityTransformer(ArticleTransformer):
    """
    Identifies ticker symbols mentioned in each article.

    Adds a `mentioned_symbols` field (list[str]) to each article dict.
    The pipeline passes these to ArticleRepository.link_symbols() to
    populate the news.article_securities table.
    """

    transform_name = "entity_extraction"

    def transform(self, articles: list[dict]) -> list[dict]:
        """
        Extract ticker mentions from each article's content.

        TODO:
            - Load the ticker → company name lookup (from findata/sources/market/tickers.json
              or directly from the market.daily_bars table)
            - For each article, search content + title for company/ticker mentions
            - Set article["mentioned_symbols"] = list of matched symbols
            - Handle articles with None content (return empty list)
            - Log a summary: how many unique tickers found across the batch
        """
        _logger.warning(
            "EntityTransformer.transform() is not yet implemented — no tickers extracted"
        )
        for article in articles:
            article["mentioned_symbols"] = []
        return articles
