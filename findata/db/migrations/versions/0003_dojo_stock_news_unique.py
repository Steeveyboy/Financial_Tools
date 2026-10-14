"""dojo_stock_news — unique (url, page_symbol), so loads can append

Revision ID: 0003_dojo_stock_news_unique
Revises: 0002_dojo_stock_news
Create Date: 2026-10-13

``load_dojo_stock_news.py`` used to replace the table on every run. It now
appends only rows it has not staged yet, using ``INSERT … ON CONFLICT DO
NOTHING`` against this index. See ``findata/models/dojo_stock_news.py``.

Existing duplicate ``(url, page_symbol)`` rows are deleted first, keeping the
lowest ``id``, or the index could not be built. Downgrading does not restore
them.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from findata.db.base import SCHEMA_NEWS

# revision identifiers, used by Alembic.
revision = "0003_dojo_stock_news_unique"
down_revision = "0002_dojo_stock_news"
branch_labels = None
depends_on = None

_INDEX_NAME = "ix_dojo_stock_news_url_page_symbol"


def upgrade() -> None:
    staged = sa.table(
        "dojo_stock_news",
        sa.column("id", sa.Integer),
        sa.column("url", sa.Text),
        sa.column("page_symbol", sa.Text),
        # op.execute() does not apply the schema_translate_map that collapses
        # schemas on SQLite, so the schema is chosen here.
        schema=None if op.get_bind().dialect.name == "sqlite" else SCHEMA_NEWS,
    )
    earlier = staged.alias("earlier")

    # EXISTS rather than NOT IN (SELECT min(id) ...): Postgres can run this as a
    # hash semi-join, where NOT IN over ~4M ids falls back to a per-row scan.
    op.execute(
        sa.delete(staged).where(
            sa.exists().where(
                earlier.c.url == staged.c.url,
                earlier.c.page_symbol == staged.c.page_symbol,
                earlier.c.id < staged.c.id,
            )
        )
    )

    op.create_index(
        _INDEX_NAME,
        "dojo_stock_news",
        ["url", "page_symbol"],
        unique=True,
        schema=SCHEMA_NEWS,
        # load_dojo_stock_news.py creates the table, index included, on a fresh
        # database, so the index may already exist by the time this runs.
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="dojo_stock_news", schema=SCHEMA_NEWS)
