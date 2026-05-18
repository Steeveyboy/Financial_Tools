"""Daily OHLCV table - daily_ohlcv

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-18 14:57:05.383868

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_ohlcv",
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("high", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("low", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("close", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("ticker", "date"),
    )


def downgrade() -> None:
    op.drop_table("daily_ohlcv")
