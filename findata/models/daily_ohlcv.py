from datetime import datetime, date
from typing import Optional

from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Numeric, Integer, String, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from findata.db.base import Base

class DailyOHLCV(Base):
    """Daily open-high-low-close-volume (OHLCV) data for a single ticker symbol.
    
    Attributes:
        ticker:     Stock ticker symbol, e.g. ``AAPL``.
        date:       Trading date (UTC).
        open:       Opening price.
        high:       High price.
        low:        Low price.
        close:      Closing price.
        volume:     Trading volume.
        fetched_at: Timestamp this row was inserted (set by the DB).
    """

    __tablename__ = "daily_ohlcv"

    
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, primary_key=True)
    open: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    high: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    low: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    close: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


    def __repr__(self) -> str:
        return f"<DailyOHLCV(ticker={self.ticker!r}, date={self.date!r})>"
