"""baseline — the whole warehouse schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-25

The single baseline for the ``resonance_desk`` rebuild. It replaces migrations
``0001_initial_schema`` … ``0004_sentiment_and_transform_log``, which were
squashed: the database is recreated from empty, so no rename or ALTER steps are
needed, and a reader sees one coherent schema rather than four incremental
patches plus renames reversing earlier decisions.

Every constraint name here comes from the ``naming_convention`` on
``findata.db.base.Base.metadata`` — do not hand-name anything, or
``alembic check`` will report drift.

See ``docs/DATA_MODEL.md`` for the naming standard and the reasoning.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from findata.db.base import ALL_SCHEMAS, SCHEMA_MARKET, SCHEMA_NEWS, SCHEMA_REFERENCE

# NOTE: timestamp defaults use sa.func.now(), never sa.text("now()").
# sa.text() is emitted verbatim, so SQLite would get `DEFAULT (now())` — a
# function it does not have — and every INSERT would fail. func.now() compiles
# per dialect: now() on Postgres, CURRENT_TIMESTAMP on SQLite.

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

#: Full-text search objects created by ``after_create`` listeners in
#: ``findata/models/company.py``. Mirrored here so ``alembic upgrade`` produces
#: the same schema as ``init_db()``. Kept in sync with
#: ``env.py::_EVENT_CREATED_OBJECTS``.
_PG_FTS_INDEX = "ix_companies_description_fts"
_SQLITE_FTS_TABLE = "companies_fts"


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Schemas — no-op on SQLite, which has none. The engine's
    # schema_translate_map collapses them there instead.
    # ------------------------------------------------------------------
    if not _is_sqlite():
        for schema in ALL_SCHEMAS:
            op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

    # ------------------------------------------------------------------
    # reference — slowly-changing dimensions
    # ------------------------------------------------------------------
    op.create_table(
        "exchanges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("timezone", sa.String(length=50), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exchanges")),
        sa.UniqueConstraint("code", name=op.f("uq_exchanges_code")),
        schema=SCHEMA_REFERENCE,
    )

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("exchange_id", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("sector", sa.String(length=100), nullable=True),
        sa.Column("industry", sa.String(length=150), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("headquarters", sa.String(length=255), nullable=True),
        sa.Column("market_cap", sa.BigInteger(), nullable=True),
        sa.Column("employees", sa.Integer(), nullable=True),
        sa.Column("fiscal_year_end", sa.String(length=10), nullable=True),
        sa.Column("isin", sa.String(length=20), nullable=True),
        sa.Column("cusip", sa.String(length=20), nullable=True),
        sa.Column("cik", sa.String(length=20), nullable=True),
        sa.Column("sedar_id", sa.String(length=50), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "symbol = upper(symbol)", name=op.f("ck_companies_symbol_uppercase")
        ),
        sa.ForeignKeyConstraint(
            ["exchange_id"],
            [f"{SCHEMA_REFERENCE}.exchanges.id"],
            name=op.f("fk_companies_exchange_id_exchanges"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
        sa.UniqueConstraint(
            "symbol", "exchange_id", name=op.f("uq_companies_symbol_exchange_id")
        ),
        schema=SCHEMA_REFERENCE,
    )
    op.create_index(
        op.f("ix_companies_country"), "companies", ["country"], schema=SCHEMA_REFERENCE
    )
    op.create_index(
        op.f("ix_companies_industry"), "companies", ["industry"], schema=SCHEMA_REFERENCE
    )
    op.create_index(
        op.f("ix_companies_is_active"),
        "companies",
        ["is_active"],
        schema=SCHEMA_REFERENCE,
    )
    op.create_index(
        op.f("ix_companies_sector"), "companies", ["sector"], schema=SCHEMA_REFERENCE
    )
    op.create_index(
        op.f("ix_companies_symbol"), "companies", ["symbol"], schema=SCHEMA_REFERENCE
    )

    # Full-text search on companies.description — dialect-conditional, and
    # mirrors the event listeners in findata/models/company.py.
    if _is_sqlite():
        op.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {_SQLITE_FTS_TABLE}
            USING fts5(
                id UNINDEXED,
                name,
                description,
                content='companies',
                content_rowid='id'
            )
            """
        )
    else:
        op.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {_PG_FTS_INDEX}
            ON {SCHEMA_REFERENCE}.companies
            USING GIN (
                to_tsvector('english',
                    coalesce(name,'') || ' ' || coalesce(description,''))
            )
            """
        )

    op.create_table(
        "insiders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=True),
        sa.Column(
            "is_board_member",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_insider", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["company_id"],
            [f"{SCHEMA_REFERENCE}.companies.id"],
            name=op.f("fk_insiders_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_insiders")),
        schema=SCHEMA_REFERENCE,
    )
    op.create_index(
        op.f("ix_insiders_company_id"),
        "insiders",
        ["company_id"],
        schema=SCHEMA_REFERENCE,
    )

    # ------------------------------------------------------------------
    # market — price time series
    # ------------------------------------------------------------------
    op.create_table(
        "daily_bars",
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("high", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("low", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("close", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("adj_close", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column(
            "dividend_amount",
            sa.Numeric(precision=18, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "split_coefficient",
            sa.Numeric(precision=18, scale=6),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
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
        sa.CheckConstraint("high >= low", name=op.f("ck_daily_bars_high_ge_low")),
        sa.CheckConstraint(
            "split_coefficient > 0",
            name=op.f("ck_daily_bars_split_coefficient_positive"),
        ),
        sa.CheckConstraint(
            "symbol = upper(symbol)", name=op.f("ck_daily_bars_symbol_uppercase")
        ),
        sa.CheckConstraint("volume >= 0", name=op.f("ck_daily_bars_volume_non_negative")),
        sa.PrimaryKeyConstraint("symbol", "trade_date", name=op.f("pk_daily_bars")),
        schema=SCHEMA_MARKET,
    )
    op.create_index(
        op.f("ix_daily_bars_trade_date"),
        "daily_bars",
        ["trade_date"],
        schema=SCHEMA_MARKET,
    )

    # ------------------------------------------------------------------
    # news — articles and their derived data
    # ------------------------------------------------------------------
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("publisher", sa.String(length=255), nullable=True),
        sa.Column("ingest_source", sa.String(length=32), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_articles")),
        sa.UniqueConstraint("url", name=op.f("uq_articles_url")),
        schema=SCHEMA_NEWS,
    )
    op.create_index(
        op.f("ix_articles_published_at"),
        "articles",
        ["published_at"],
        schema=SCHEMA_NEWS,
    )

    op.create_table(
        "article_securities",
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("link_source", sa.String(length=32), nullable=False),
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
        sa.CheckConstraint(
            "symbol = upper(symbol)",
            name=op.f("ck_article_securities_symbol_uppercase"),
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            [f"{SCHEMA_NEWS}.articles.id"],
            name=op.f("fk_article_securities_article_id_articles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "article_id", "symbol", name=op.f("pk_article_securities")
        ),
        schema=SCHEMA_NEWS,
    )
    op.create_index(
        "ix_article_securities_symbol_article_id",
        "article_securities",
        ["symbol", "article_id"],
        schema=SCHEMA_NEWS,
    )

    op.create_table(
        "article_transforms",
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("transform_name", sa.String(length=64), nullable=False),
        sa.Column(
            "transformed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            [f"{SCHEMA_NEWS}.articles.id"],
            name=op.f("fk_article_transforms_article_id_articles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "article_id", "transform_name", name=op.f("pk_article_transforms")
        ),
        schema=SCHEMA_NEWS,
    )
    op.create_index(
        "ix_article_transforms_transform_name_article_id",
        "article_transforms",
        ["transform_name", "article_id"],
        schema=SCHEMA_NEWS,
    )


def downgrade() -> None:
    op.drop_table("article_transforms", schema=SCHEMA_NEWS)
    op.drop_table("article_securities", schema=SCHEMA_NEWS)
    op.drop_table("articles", schema=SCHEMA_NEWS)
    op.drop_table("daily_bars", schema=SCHEMA_MARKET)
    op.drop_table("insiders", schema=SCHEMA_REFERENCE)

    # Search objects must go before the table they shadow.
    if _is_sqlite():
        op.execute(f"DROP TABLE IF EXISTS {_SQLITE_FTS_TABLE}")
    else:
        op.execute(f"DROP INDEX IF EXISTS {SCHEMA_REFERENCE}.{_PG_FTS_INDEX}")

    op.drop_table("companies", schema=SCHEMA_REFERENCE)
    op.drop_table("exchanges", schema=SCHEMA_REFERENCE)

    if not _is_sqlite():
        for schema in reversed(ALL_SCHEMAS):
            op.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
