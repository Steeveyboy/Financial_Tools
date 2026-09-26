"""
models/daily_bar.py

Daily OHLCV bars.

Renamed from ``daily_ohlcv``: plural per the naming standard, and ``bars``
generalizes to the ``intraday_bars`` this will eventually sit beside.

The adjustment columns are the substantive addition. The previous table stored
only raw OHLC, which makes a correct return impossible to compute from it: a 4:1
split reads as a −75% one-day move and dividends vanish entirely. Research built
on that is wrong in a way that looks like a finding, not like a bug.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, Date, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from findata.db.base import SCHEMA_MARKET, Base
from findata.models.mixins import TimestampMixin

#: Prices use 6 decimal places rather than 4: adjusted closes of long histories
#: get very small, and adjustment factors carry more precision than a traded
#: price does.
_PRICE = Numeric(18, 6)


class DailyBar(TimestampMixin, Base):
    """One security's OHLCV for one trading day."""

    __tablename__ = "daily_bars"

    #: Symbol, not a ``security_id``. Phase 8 of ``docs/CLEANUP_PLAN.md``
    #: replaces this with a foreign key to a security master once a source
    #: exists that can populate one; until then this is an unconstrained string
    #: and joins against it are string joins. Stored uppercase so that a join
    #: to ``news.article_securities.symbol`` cannot miss on case.
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)

    #: Was ``date``, which shadowed the Python builtin at every call site.
    trade_date: Mapped[date_type] = mapped_column(Date, primary_key=True, index=True)

    # ------------------------------------------------------------------
    # As-traded prices
    # ------------------------------------------------------------------
    # open/high/low/close collide with SQL keywords and are quoted by
    # SQLAlchemy. They keep these names because every consumer of a bar table
    # expects exactly them; `open_price` would be worse.
    open: Mapped[Optional[Decimal]] = mapped_column(_PRICE)
    high: Mapped[Optional[Decimal]] = mapped_column(_PRICE)
    low: Mapped[Optional[Decimal]] = mapped_column(_PRICE)
    close: Mapped[Optional[Decimal]] = mapped_column(_PRICE)
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)

    # ------------------------------------------------------------------
    # Adjustment
    # ------------------------------------------------------------------
    #: Split- and dividend-adjusted close. **Use this for returns**, never
    #: ``close``. Provider-supplied, so the methodology is theirs.
    adj_close: Mapped[Optional[Decimal]] = mapped_column(_PRICE)

    #: Cash distribution with an ex-date of ``trade_date``; 0 on most days.
    dividend_amount: Mapped[Decimal] = mapped_column(
        _PRICE, nullable=False, server_default=text("0")
    )

    #: Split ratio effective ``trade_date``; 1 on most days. A 4:1 split is 4.
    split_coefficient: Mapped[Decimal] = mapped_column(
        _PRICE, nullable=False, server_default=text("1")
    )

    #: Which provider supplied the bar — adjustment methodology differs between
    #: them, so mixing sources in one series without knowing is a silent error.
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        # Cheap provider-glitch traps, enforced at write time instead of
        # discovered in a backtest. NULL columns make these evaluate to unknown,
        # which passes — partial bars are still allowed.
        CheckConstraint("high >= low", name="high_ge_low"),
        CheckConstraint("volume >= 0", name="volume_non_negative"),
        CheckConstraint("split_coefficient > 0", name="split_coefficient_positive"),
        CheckConstraint("symbol = upper(symbol)", name="symbol_uppercase"),
        {"schema": SCHEMA_MARKET},
    )

    def __repr__(self) -> str:
        return f"<DailyBar(symbol={self.symbol!r}, trade_date={self.trade_date!r})>"
