"""
transformers/sentiment.py

Sentiment analysis transformer backed by FinBERT.

Scores each article's tone and attaches it as ``sentiment_score``. The score
is persisted to ``articles.sentiment_score`` by
:meth:`~findata.sources.news.pipeline.TransformationPipeline._persist`.

Model
-----
`ProsusAI/finbert <https://huggingface.co/ProsusAI/finbert>`_ — BERT fine-tuned
on financial news, producing ``positive`` / ``negative`` / ``neutral``
probabilities. Runs locally; no API calls leave this process.

Score convention
----------------
``sentiment_score = P(positive) - P(negative)``, giving a signed value in
``[-1.0, 1.0]``:

    +1.0   unambiguously positive
     0.0   neutral, or positive and negative in balance
    -1.0   unambiguously negative

Signed-and-centred is deliberate. The analytical goal is to test whether tone
predicts price movement, and a signed score lines up with signed returns —
neutral sits at zero rather than at an arbitrary 0.5 midpoint, so the sign of
the score and the sign of the return are directly comparable.

Note this collapses "confidently neutral" and "torn between positive and
negative" to the same value. Both are genuinely uninformative for a directional
signal, so the collapse is acceptable; if the distinction ever matters, store
the three class probabilities rather than trying to encode them in one float.

Cost
----
FinBERT is a 110M-parameter model. Expect roughly 50–150 articles/second on
CPU and 10–30x that on GPU — so the full ~1.9M-row FNSPID set is hours of
compute. The pipeline pages through ``get_untransformed()`` and logs every
batch to ``transform_log``, so a run can be interrupted and resumed without
rescoring what it already covered.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import ArticleTransformer

_logger = logging.getLogger(__name__)

#: HuggingFace model id. FinBERT is fine-tuned on financial text — a
#: general-purpose sentiment model materially underperforms on this domain.
DEFAULT_MODEL = "ProsusAI/finbert"

#: FinBERT inherits BERT's 512-token limit. Headlines are far shorter; article
#: bodies get truncated, which is fine — lede paragraphs carry the tone.
MAX_TOKENS = 512


class SentimentTransformer(ArticleTransformer):
    """Adds a signed ``sentiment_score`` in ``[-1.0, 1.0]`` to each article.

    The model is loaded lazily on first use so that importing this module —
    which the pipeline does at startup — doesn't pull in ``torch`` or download
    weights until a transform actually runs.

    Args:
        model_name: HuggingFace model id (default :data:`DEFAULT_MODEL`).
        batch_size: Articles per forward pass. Raise it on a GPU; lower it if
                    you hit memory pressure.
        device:     ``"cpu"``, ``"cuda"``, or ``None`` to auto-detect.
    """

    transform_id = "sentiment"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        batch_size: int = 32,
        device: str | None = None,
    ):
        self.model_name = model_name
        self.batch_size = batch_size
        self._device = device
        self._model: Any = None
        self._tokenizer: Any = None
        self._label_index: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _ensure_model(self) -> None:
        """Load the tokenizer and model on first use (idempotent)."""
        if self._model is not None:
            return

        try:
            import torch
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ImportError(
                "SentimentTransformer requires torch and transformers. "
                "Install them with:\n"
                "    pip install -r findata/sources/news/requirements.txt"
            ) from exc

        if self._device is None:
            self._device = "cuda" if torch.cuda.is_available() else "cpu"

        _logger.info(
            "Loading sentiment model '%s' on %s (first run downloads weights)",
            self.model_name,
            self._device,
        )
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name
        )
        self._model.to(self._device)
        self._model.eval()

        # Resolve label positions from the model config rather than assuming
        # an ordering — FinBERT forks differ in how they order the three
        # classes, and a wrong assumption silently inverts every score.
        self._label_index = {
            label.lower(): idx
            for idx, label in self._model.config.id2label.items()
        }
        missing = {"positive", "negative"} - self._label_index.keys()
        if missing:
            raise ValueError(
                f"Model '{self.model_name}' is missing expected sentiment "
                f"label(s) {sorted(missing)}; got "
                f"{sorted(self._label_index)}. This transformer expects a "
                "positive/negative/neutral classifier such as FinBERT."
            )
        _logger.info("Sentiment model ready — labels: %s", sorted(self._label_index))

    # ------------------------------------------------------------------
    # Text selection
    # ------------------------------------------------------------------

    @staticmethod
    def _article_text(article: dict) -> str | None:
        """Return the text to score, or ``None`` if the article has none.

        The headline leads: it is the most tone-dense part of a financial news
        item and, being first, it survives truncation. Body text follows as
        supporting context when present.
        """
        title = (article.get("title") or "").strip()
        content = (article.get("content") or "").strip()

        if title and content:
            return f"{title}. {content}"
        return title or content or None

    # ------------------------------------------------------------------
    # Transform
    # ------------------------------------------------------------------

    def transform(self, articles: list[dict]) -> list[dict]:
        """Score each article and attach ``sentiment_score``.

        Articles with no usable text get ``None``. The pipeline still logs
        them to ``transform_log``, so they are not retried indefinitely.

        Args:
            articles: Article dicts from the repository.

        Returns:
            The same list, each dict carrying a ``sentiment_score``.
        """
        if not articles:
            return articles

        self._ensure_model()

        # Partition into scorable and empty, keeping indices so results can be
        # written back to the right dicts.
        scorable: list[int] = []
        texts: list[str] = []
        for idx, article in enumerate(articles):
            text = self._article_text(article)
            if text is None:
                article["sentiment_score"] = None
            else:
                scorable.append(idx)
                texts.append(text)

        empty = len(articles) - len(scorable)
        if empty:
            _logger.info("%d/%d articles have no text to score", empty, len(articles))

        scores: list[float] = []
        for start in range(0, len(texts), self.batch_size):
            scores.extend(self._score_batch(texts[start : start + self.batch_size]))

        for idx, score in zip(scorable, scores):
            articles[idx]["sentiment_score"] = score

        self._log_summary(scores)
        return articles

    def _score_batch(self, texts: list[str]) -> list[float]:
        """Run one forward pass and return signed scores for *texts*."""
        import torch

        encoded = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=MAX_TOKENS,
            return_tensors="pt",
        ).to(self._device)

        with torch.no_grad():
            logits = self._model(**encoded).logits
            probs = torch.softmax(logits, dim=-1)

        positive = probs[:, self._label_index["positive"]]
        negative = probs[:, self._label_index["negative"]]
        return (positive - negative).cpu().tolist()

    @staticmethod
    def _log_summary(scores: list[float]) -> None:
        """Log min/max/mean for a scored batch — a cheap sanity check.

        A mean pinned near zero across a large batch usually means the model
        is seeing empty or truncated-to-nothing text.
        """
        if not scores:
            return
        _logger.info(
            "Scored %d articles — min %.3f, max %.3f, mean %.3f",
            len(scores),
            min(scores),
            max(scores),
            sum(scores) / len(scores),
        )
