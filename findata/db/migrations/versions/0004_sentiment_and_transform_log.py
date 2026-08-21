"""Sentiment transform — articles.sentiment_score, transform_log

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-21 00:00:00.000000

Adds the storage the ``sentiment`` transform needs:

* ``articles.sentiment_score`` — signed tone in ``[-1.0, 1.0]``, nullable.
* ``transform_log``            — one row per (article, transform) processed,
                                 so Phase 2 can resume and so a NULL score can
                                 be told apart from an unscored article.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("sentiment_score", sa.Float(), nullable=True),
    )

    op.create_table(
        "transform_log",
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("transform_id", sa.String(64), nullable=False),
        sa.Column(
            "transformed_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("article_id", "transform_id"),
    )
    op.create_index(
        "ix_transform_log_transform_article",
        "transform_log",
        ["transform_id", "article_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transform_log_transform_article", table_name="transform_log"
    )
    op.drop_table("transform_log")
    op.drop_column("articles", "sentiment_score")
