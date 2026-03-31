"""SQLAlchemy declarative models for company data.

These models define the PostgreSQL table schemas for storing
company descriptions, metadata, and officers.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Shared declarative base for all data-warehouse models."""

    pass


class Company(Base):
    """Core company profile and description."""

    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), unique=True, nullable=False, index=True)
    short_name = Column(String(255))
    long_name = Column(String(255))
    business_summary = Column(Text)
    sector = Column(String(100))
    industry = Column(String(100))
    country = Column(String(100))
    city = Column(String(100))
    state = Column(String(50))
    zip_code = Column(String(20))
    address = Column(String(500))
    phone = Column(String(50))
    website = Column(String(500))
    full_time_employees = Column(Integer)
    market_cap = Column(BigInteger)
    exchange = Column(String(50))
    currency = Column(String(10))
    quote_type = Column(String(50))
    ipo_year = Column(Integer)

    # Financial snapshot (trailing twelve months)
    trailing_pe = Column(Float)
    forward_pe = Column(Float)
    dividend_yield = Column(Float)
    beta = Column(Float)
    fifty_two_week_high = Column(Float)
    fifty_two_week_low = Column(Float)
    revenue = Column(BigInteger)
    ebitda = Column(BigInteger)
    net_income = Column(BigInteger)
    profit_margin = Column(Float)

    fetched_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    officers = relationship(
        "CompanyOfficer",
        back_populates="company",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Company(symbol={self.symbol!r}, name={self.short_name!r})>"


class CompanyOfficer(Base):
    """Executive / officer associated with a company."""

    __tablename__ = "company_officers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_symbol = Column(
        String(10),
        ForeignKey("companies.symbol", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255))
    title = Column(String(255))
    age = Column(Integer)
    year_born = Column(Integer)
    fiscal_year = Column(Integer)
    total_pay = Column(BigInteger)
    exercised_value = Column(BigInteger)
    unexercised_value = Column(BigInteger)

    company = relationship("Company", back_populates="officers")

    def __repr__(self) -> str:
        return f"<CompanyOfficer(name={self.name!r}, title={self.title!r})>"
