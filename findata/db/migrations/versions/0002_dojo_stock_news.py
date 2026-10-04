"""dojo_stock_news — staging table for AlphaDojo/dojo_stock_news

Revision ID: 0002_dojo_stock_news
Revises: 0001_baseline
Create Date: 2026-10-04

A raw, undeduplicated copy of the HuggingFace dataset, loaded by
``load_dojo_stock_news.py``. See ``findata/models/dojo_stock_news.py``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from findata.db.base import SCHEMA_NEWS

# revision identifiers, used by Alembic.
revision = "0002_dojo_stock_news"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dojo_stock_news",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("publisher", sa.Text(), nullable=True),
        sa.Column("publish_date", sa.Text(), nullable=True),
        sa.Column("ago", sa.Text(), nullable=True),
        sa.Column("page_symbol", sa.Text(), nullable=True),
        sa.Column("primarysymbol", sa.Text(), nullable=True),
        sa.Column("on_symbol_json", sa.Text(), nullable=True),
        sa.Column("primarytopic", sa.Text(), nullable=True),
        sa.Column("primarytopic_url", sa.Text(), nullable=True),
        sa.Column("image", sa.Text(), nullable=True),
        sa.Column("imagedomain", sa.Text(), nullable=True),
        sa.Column("publisher_logo", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dojo_stock_news")),
        schema=SCHEMA_NEWS,
        # load_dojo_stock_news.py creates this table itself if it's missing,
        # so it may already exist by the time this migration runs.
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("dojo_stock_news", schema=SCHEMA_NEWS)
