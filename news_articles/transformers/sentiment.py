"""
transformers/sentiment.py

Sentiment analysis transformer stub.

Assigns a sentiment score to each article based on its content.
The score will be stored back to the articles table (requires a schema
migration to add a `sentiment_score` FLOAT column).

This is one of the core analytical goals of Resonance Desk: once sentiment
scores are available alongside market price data, we can begin modelling
whether article tone predicts price movement.

There is already a trained sentiment model in SentimentAnalysis/sentiment/
(a scikit-learn pipeline serialised to a pickle file). That model was trained
on Yelp reviews, which may not transfer well to financial news. Options:

    Option A — Reuse existing model (fast, lower quality)
        Load SentimentAnalysis/sentiment/sentiment_pipeline.pickle
        Apply to article content

    Option B — Use a pretrained financial NLP model (recommended)
        FinBERT (ProsusAI/finbert) is fine-tuned on financial news and
        produces positive / negative / neutral scores. Available via
        HuggingFace transformers.

    Option C — Zero-shot with a general LLM
        Use the Claude API to score sentiment and return structured output.
        Higher latency and cost but requires no training data.

To implement:
    1. Choose an approach above
    2. Add the required dependency to requirements.txt
    3. Fill in the `transform()` method
    4. Add a migration to add `sentiment_score FLOAT` to the articles table
"""

from __future__ import annotations

import logging

from .base import ArticleTransformer

_logger = logging.getLogger(__name__)


class SentimentTransformer(ArticleTransformer):
    """
    Adds a `sentiment_score` field (float, 0.0–1.0) to each article dict.

    A score near 1.0 indicates positive sentiment; near 0.0 is negative.
    """

    transform_id = "sentiment"

    def transform(self, articles: list[dict]) -> list[dict]:
        """
        Score each article's content and attach the result as `sentiment_score`.

        TODO:
            - Load the chosen model (see module docstring for options)
            - For each article, run model.predict_proba([article["content"]])
            - Set article["sentiment_score"] = float score
            - Handle articles with empty or None content gracefully (score = None)
            - Log a summary: min/max/mean scores for the batch
        """
        _logger.warning(
            "SentimentTransformer.transform() is not yet implemented — scores not applied"
        )
        for article in articles:
            article["sentiment_score"] = None
        return articles
