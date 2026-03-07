"""
Company model — represents a corporate profile listed on a stock exchange.

Full-text search support:
  * **PostgreSQL**: a GIN index is created via a DDL ``after_create`` event
    listener on ``to_tsvector('english', name || ' ' || description)``.
  * **SQLite**: an FTS5 virtual table ``company_fts`` (mirroring ``id``,
    ``name``, and ``description``) is created via the same mechanism.

Both are handled by :func:`_create_fts` at the bottom of this module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from .base import Base

if TYPE_CHECKING:
    from .exchange import Exchange
    from .insider import Insider


class Company(Base):
    """Corporate profile entity.

    Attributes:
        id:             Auto-incrementing primary key.
        name:           Legal company name.
        ticker:         Stock ticker symbol (e.g. ``AAPL``).
        exchange_id:    FK to :class:`~corporate_db.models.exchange.Exchange`.
        country:        Country of incorporation.
        sector:         GICS sector classification.
        industry:       GICS industry classification.
        description:    Full business description — indexed for full-text search.
        website:        Corporate website URL.
        headquarters:   City, Province/State string.
        market_cap:     Market capitalisation in the exchange's base currency.
        employees:      Approximate employee headcount.
        fiscal_year_end: e.g. ``December 31``.
        isin:           International Securities Identification Number.
        cusip:          CUSIP identifier (US/Canada).
        cik:            SEC Central Index Key (US companies only).
        sedar_id:       SEDAR+ profile ID (Canadian companies only).
        is_active:      Whether the listing is currently active.
        created_at:     Record creation timestamp (UTC).
        updated_at:     Last-modified timestamp, auto-updated on every write (UTC).
        exchange:       Parent exchange (many-to-one).
        insiders:       Board members / insiders associated with the company.
    """

    __tablename__ = "companies"

    # ------------------------------------------------------------------
    # Primary key
    # ------------------------------------------------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------
    # Core identification
    # ------------------------------------------------------------------
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    exchange_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("exchanges.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    # ------------------------------------------------------------------
    # Descriptive / searchable
    # ------------------------------------------------------------------
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    headquarters: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # ------------------------------------------------------------------
    # Financial data
    # ------------------------------------------------------------------
    market_cap: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    employees: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fiscal_year_end: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # ------------------------------------------------------------------
    # External identifiers
    # ------------------------------------------------------------------
    isin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    cusip: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    cik: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sedar_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # ------------------------------------------------------------------
    # Status / audit
    # ------------------------------------------------------------------
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ------------------------------------------------------------------
    # Table-level constraints
    # ------------------------------------------------------------------
    __table_args__ = (
        # Enforce uniqueness of ticker within an exchange
        UniqueConstraint("ticker", "exchange_id", name="uq_company_ticker_exchange"),
        # Scalar indexes for common filter/sort columns
        Index("ix_company_ticker", "ticker"),
        Index("ix_company_country", "country"),
        Index("ix_company_sector", "sector"),
        Index("ix_company_industry", "industry"),
        Index("ix_company_is_active", "is_active"),
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    exchange: Mapped["Exchange"] = relationship("Exchange", back_populates="companies")
    insiders: Mapped[List["Insider"]] = relationship(
        "Insider",
        back_populates="company",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Company(ticker={self.ticker!r}, name={self.name!r})>"


# ---------------------------------------------------------------------------
# Full-text search — dialect-conditional DDL event listeners
# ---------------------------------------------------------------------------
# We use event listeners rather than a static Index object so that the correct
# DDL is emitted for each backend:
#
#  * PostgreSQL: GIN index on ``to_tsvector('english', name || ' ' || description)``
#  * SQLite: FTS5 virtual table ``company_fts`` (SQLite has no GIN support)
#
# The Alembic migration (0001_initial_schema.py) mirrors this logic for
# production deployments managed by ``alembic upgrade head``.


@event.listens_for(Company.__table__, "after_create")
def _create_fts(target, connection, **kw):  # noqa: ARG001
    """Create the appropriate full-text search index after the table is created."""
    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_company_description_fts
                ON companies
                USING GIN (
                    to_tsvector('english',
                        coalesce(name,'') || ' ' || coalesce(description,''))
                )
                """
            )
        )
    elif connection.dialect.name == "sqlite":
        connection.execute(
            text(
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
        )


@event.listens_for(Company.__table__, "before_drop")
def _drop_fts(target, connection, **kw):  # noqa: ARG001
    """Drop the full-text search index/table before the companies table is dropped."""
    if connection.dialect.name == "postgresql":
        connection.execute(text("DROP INDEX IF EXISTS ix_company_description_fts"))
    elif connection.dialect.name == "sqlite":
        connection.execute(text("DROP TABLE IF EXISTS company_fts"))
