"""News tables — articles, article_tickers.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-11 00:00:00.000000

Adds the news ETL tables (previously defined as standalone SQLAlchemy Core
tables in ``news_articles/db/schema.py``):

* ``articles``        — one row per ingested article, deduplicated by URL
* ``article_tickers`` — many-to-many link between articles and tickers,
                        with composite primary key ``(article_id, ticker)``
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("publisher", sa.String(255), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", name="uq_articles_url"),
    )
    op.create_index("ix_articles_published_at", "articles", ["published_at"])

    op.create_table(
        "article_tickers",
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("article_id", "ticker"),
    )
    op.create_index(
        "ix_article_tickers_ticker_article",
        "article_tickers",
        ["ticker", "article_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_article_tickers_ticker_article", table_name="article_tickers")
    op.drop_table("article_tickers")
    op.drop_index("ix_articles_published_at", table_name="articles")
    op.drop_table("articles")
