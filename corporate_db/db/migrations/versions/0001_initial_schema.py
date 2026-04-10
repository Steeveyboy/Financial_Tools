"""Initial schema — exchanges, companies, insiders.

Revision ID: 0001
Revises:
Create Date: 2026-03-07 00:00:00.000000

Creates the three core tables:

* ``exchanges``  — stock exchange reference data
* ``companies``  — corporate profiles with full-text search support
* ``insiders``   — board member / insider stub (Agent 7)

Dialect notes
-------------
* PostgreSQL: a GIN index is added on ``to_tsvector('english', ...)`` over
  ``companies.name`` and ``companies.description``.
* SQLite: the FTS5 virtual table ``company_fts`` is created via a raw DDL
  statement (SQLite does not support GIN indexes).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # exchanges
    # ------------------------------------------------------------------
    op.create_table(
        "exchanges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("timezone", sa.String(50), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_exchange_code"),
    )

    # ------------------------------------------------------------------
    # companies
    # ------------------------------------------------------------------
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("exchange_id", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("industry", sa.String(150), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),
        sa.Column("headquarters", sa.String(255), nullable=True),
        sa.Column("market_cap", sa.BigInteger(), nullable=True),
        sa.Column("employees", sa.Integer(), nullable=True),
        sa.Column("fiscal_year_end", sa.String(10), nullable=True),
        sa.Column("isin", sa.String(20), nullable=True),
        sa.Column("cusip", sa.String(20), nullable=True),
        sa.Column("cik", sa.String(20), nullable=True),
        sa.Column("sedar_id", sa.String(50), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="1",
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
        sa.ForeignKeyConstraint(
            ["exchange_id"],
            ["exchanges.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "exchange_id", name="uq_company_ticker_exchange"),
    )

    # Scalar indexes
    op.create_index("ix_company_ticker",    "companies", ["ticker"])
    op.create_index("ix_company_country",   "companies", ["country"])
    op.create_index("ix_company_sector",    "companies", ["sector"])
    op.create_index("ix_company_industry",  "companies", ["industry"])
    op.create_index("ix_company_is_active", "companies", ["is_active"])

    # PostgreSQL-only: GIN full-text search index
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE INDEX ix_company_description_fts
            ON companies
            USING GIN (
                to_tsvector('english',
                    coalesce(name,'') || ' ' || coalesce(description,''))
            )
            """
        )
    elif bind.dialect.name == "sqlite":
        # SQLite FTS5 virtual table
        op.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS company_fts
            USING fts5(
                id UNINDEXED,
                name,
                description,
                content='companies',
                content_rowid='id'
            )
            """
        )

    # ------------------------------------------------------------------
    # insiders
    # ------------------------------------------------------------------
    op.create_table(
        "insiders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column(
            "is_board_member",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_insider",
            sa.Boolean(),
            nullable=False,
            server_default="1",
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
            ["companies.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_insiders_company_id", "insiders", ["company_id"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_index("ix_insiders_company_id", table_name="insiders")
    op.drop_table("insiders")

    op.drop_index("ix_company_is_active", table_name="companies")
    op.drop_index("ix_company_industry",  table_name="companies")
    op.drop_index("ix_company_sector",    table_name="companies")
    op.drop_index("ix_company_country",   table_name="companies")
    op.drop_index("ix_company_ticker",    table_name="companies")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_company_description_fts")
    elif bind.dialect.name == "sqlite":
        op.execute("DROP TABLE IF EXISTS company_fts")

    op.drop_table("companies")
    op.drop_table("exchanges")
