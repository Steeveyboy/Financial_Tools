-- =============================================================================
-- corporate_db — PostgreSQL DDL reference
-- =============================================================================
-- This file documents the intended schema in plain SQL (PostgreSQL dialect).
-- It is for reference / manual use only.  All schema changes should be
-- managed through Alembic migrations.
--
-- Generate from models:
--   python -c "
--   from sqlalchemy.schema import CreateTable
--   from corporate_db.models import Base, Exchange, Company, Insider
--   from sqlalchemy.dialects import postgresql
--   for t in Base.metadata.sorted_tables:
--       print(CreateTable(t).compile(dialect=postgresql.dialect()))
--   "
-- =============================================================================

-- ---------------------------------------------------------------------------
-- exchanges
-- ---------------------------------------------------------------------------
CREATE TABLE exchanges (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(20)  NOT NULL UNIQUE,
    name        VARCHAR(100) NOT NULL,
    country     VARCHAR(100),
    currency    VARCHAR(10),
    timezone    VARCHAR(50),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  exchanges             IS 'Stock exchanges (NYSE, NASDAQ, TSX, TSXV, …)';
COMMENT ON COLUMN exchanges.code       IS 'Short exchange code, e.g. NYSE, NASDAQ, TSX';
COMMENT ON COLUMN exchanges.name       IS 'Full exchange name';
COMMENT ON COLUMN exchanges.country    IS 'Country of domicile';
COMMENT ON COLUMN exchanges.currency   IS 'Primary trading currency code, e.g. USD, CAD';
COMMENT ON COLUMN exchanges.timezone   IS 'IANA timezone, e.g. America/New_York';

-- ---------------------------------------------------------------------------
-- companies
-- ---------------------------------------------------------------------------
CREATE TABLE companies (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(255) NOT NULL,
    ticker           VARCHAR(20)  NOT NULL,
    exchange_id      INTEGER      NOT NULL REFERENCES exchanges(id) ON DELETE RESTRICT,

    -- Classification
    country          VARCHAR(100),
    sector           VARCHAR(100),
    industry         VARCHAR(150),

    -- Descriptive
    description      TEXT,
    website          VARCHAR(255),
    headquarters     VARCHAR(255),

    -- Financial
    market_cap       BIGINT,
    employees        INTEGER,
    fiscal_year_end  VARCHAR(10),

    -- External identifiers
    isin             VARCHAR(20),
    cusip            VARCHAR(20),
    cik              VARCHAR(20),
    sedar_id         VARCHAR(50),

    -- Status / audit
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_company_ticker_exchange UNIQUE (ticker, exchange_id)
);

COMMENT ON TABLE  companies                  IS 'Corporate profiles listed on stock exchanges';
COMMENT ON COLUMN companies.ticker           IS 'Stock ticker symbol';
COMMENT ON COLUMN companies.exchange_id      IS 'FK to exchanges.id';
COMMENT ON COLUMN companies.description      IS 'Full business description — indexed for FTS';
COMMENT ON COLUMN companies.isin             IS 'International Securities Identification Number';
COMMENT ON COLUMN companies.cusip            IS 'CUSIP identifier (US / Canada)';
COMMENT ON COLUMN companies.cik             IS 'SEC Central Index Key (US companies only)';
COMMENT ON COLUMN companies.sedar_id         IS 'SEDAR+ profile ID (Canadian companies only)';

-- Scalar indexes
CREATE INDEX ix_company_ticker    ON companies (ticker);
CREATE INDEX ix_company_country   ON companies (country);
CREATE INDEX ix_company_sector    ON companies (sector);
CREATE INDEX ix_company_industry  ON companies (industry);
CREATE INDEX ix_company_is_active ON companies (is_active);

-- PostgreSQL full-text search: GIN index over name + description
CREATE INDEX ix_company_description_fts
    ON companies
    USING GIN (
        to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,''))
    );

-- ---------------------------------------------------------------------------
-- insiders  (stub — will be extended by Agent 7)
-- ---------------------------------------------------------------------------
CREATE TABLE insiders (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER     NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    role            VARCHAR(100),
    is_board_member BOOLEAN     NOT NULL DEFAULT FALSE,
    is_insider      BOOLEAN     NOT NULL DEFAULT TRUE,
    start_date      DATE,
    end_date        DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_insiders_company_id ON insiders (company_id);

COMMENT ON TABLE  insiders                   IS 'Board members and reporting insiders (stub — Agent 7)';
COMMENT ON COLUMN insiders.company_id        IS 'FK to companies.id';
COMMENT ON COLUMN insiders.is_board_member   IS 'True if the person sits on the board of directors';
COMMENT ON COLUMN insiders.is_insider        IS 'True if the person is a reporting insider';
COMMENT ON COLUMN insiders.start_date        IS 'Date the role began (nullable)';
COMMENT ON COLUMN insiders.end_date          IS 'Date the role ended; NULL means current';

-- =============================================================================
-- SQLite note
-- =============================================================================
-- When using SQLite, the following FTS5 virtual table is created automatically
-- by corporate_db.db.connection.init_db():
--
--   CREATE VIRTUAL TABLE company_fts
--   USING fts5(
--       id UNINDEXED,
--       name,
--       description,
--       content='companies',
--       content_rowid='id'
--   );
-- =============================================================================
