"""
stats.py

Aggregate statistics over the articles table.

To add a new statistic:
  1. Add a method to ArticleRepository (db/repository.py) that computes it.
  2. Add a (label, method) entry to STATS below.

compute_stats() then picks it up automatically — nothing else needs to change.
"""

from __future__ import annotations

from typing import Callable

from .db.repository import ArticleRepository

Stat = Callable[[ArticleRepository], object]

# Each entry is (display label, ArticleRepository method to call).
STATS: list[tuple[str, Stat]] = [
    ("Total articles", ArticleRepository.count_articles),
    ("Unique publishers", ArticleRepository.count_unique_publishers),
]


def compute_stats(repo: ArticleRepository) -> list[tuple[str, object]]:
    """Run every registered statistic against `repo` and return (label, value) pairs."""
    return [(label, stat(repo)) for label, stat in STATS]
