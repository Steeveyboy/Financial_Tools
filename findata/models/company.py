"""
models/company.py

The issuer — a legal entity whose securities trade on an exchange.

Full-text search on ``description`` is dialect-conditional and created by
``after_create`` event listeners at the bottom of this module:

  * **PostgreSQL** — a GIN index on
    ``to_tsvector('english', name || ' ' || description)``.
  * **SQLite** — an FTS5 virtual table ``companies_fts``.

Neither is declared on the model, so Alembic autogenerate cannot see them and
reports them as "removed". Both names are listed in
``findata/db/migrations/env.py``'s ``_EVENT_CREATED_OBJECTS`` to suppress the
``DROP`` this would otherwise generate. **Any new event-listener DDL must be
added there too.**
"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from findata.db.base import SCHEMA_REFERENCE, Base
from findata.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from .exchange import Exchange
    from .insider import Insider


class Company(TimestampMixin, Base):
    """A listed issuer.

    ``symbol`` + ``exchange_id`` live here for now. They are really attributes
    of a *security*, not of an issuer — an issuer with two share classes has two
    symbols — so Phase 8 of ``docs/CLEANUP_PLAN.md`` moves them onto a
    ``reference.securities`` table. Until a source exists that can populate a
    security master, they stay.
    """

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    #: Traded symbol. ``String(32)`` is the warehouse-wide width — it holds
    #: share-class and venue suffixes (``BRK.B``, ``RY.TO``) with room to spare.
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    exchange_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{SCHEMA_REFERENCE}.exchanges.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    industry: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, index=True)

    # ------------------------------------------------------------------
    # Descriptive
    # ------------------------------------------------------------------
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    headquarters: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # ------------------------------------------------------------------
    # Fundamentals
    # ------------------------------------------------------------------
    #: Point-in-time snapshot, overwritten on refresh — **not** a time series.
    #: A real history belongs in a ``reference.company_fundamentals`` table; see
    #: the known-gaps table in ``docs/DATA_MODEL.md``.
    market_cap: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    employees: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fiscal_year_end: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # ------------------------------------------------------------------
    # External identifiers
    # ------------------------------------------------------------------
    isin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    cusip: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    #: SEC Central Index Key — the join key for Phase 6 SEC ingestion.
    cik: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    #: SEDAR+ profile id (Canadian issuers).
    sedar_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), index=True
    )

    __table_args__ = (
        UniqueConstraint("symbol", "exchange_id"),
        # Symbols are stored uppercase everywhere so that string joins between
        # tables loaded by different pipelines cannot miss on case alone.
        CheckConstraint("symbol = upper(symbol)", name="symbol_uppercase"),
        {"schema": SCHEMA_REFERENCE},
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
        return f"<Company(symbol={self.symbol!r}, name={self.name!r})>"


# ---------------------------------------------------------------------------
# Full-text search — dialect-conditional DDL
# ---------------------------------------------------------------------------
# Event listeners rather than a declared Index, because the correct DDL differs
# per backend and SQLite has no GIN. 0001_baseline.py mirrors this for
# `alembic upgrade head`.

_PG_FTS_INDEX = "ix_companies_description_fts"
_SQLITE_FTS_TABLE = "companies_fts"


@event.listens_for(Company.__table__, "after_create")
def _create_fts(target, connection, **kw):  # noqa: ARG001
    """Create the full-text search index/table after ``companies`` is created."""
    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                f"""
                CREATE INDEX IF NOT EXISTS {_PG_FTS_INDEX}
                ON {SCHEMA_REFERENCE}.companies
                USING GIN (
                    to_tsvector('english',
                        coalesce(name,'') || ' ' || coalesce(description,''))
                )
                """
            )
        )
    elif connection.dialect.name == "sqlite":
        # No schema qualifier: on SQLite every schema collapses to the default
        # one via schema_translate_map (findata.db.base).
        connection.execute(
            text(
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
        )


@event.listens_for(Company.__table__, "before_drop")
def _drop_fts(target, connection, **kw):  # noqa: ARG001
    """Drop the search index/table before ``companies`` is dropped."""
    if connection.dialect.name == "postgresql":
        connection.execute(
            text(f"DROP INDEX IF EXISTS {SCHEMA_REFERENCE}.{_PG_FTS_INDEX}")
        )
    elif connection.dialect.name == "sqlite":
        connection.execute(text(f"DROP TABLE IF EXISTS {_SQLITE_FTS_TABLE}"))
