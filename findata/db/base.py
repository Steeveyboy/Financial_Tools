"""
Shared declarative base, naming conventions, and schema layout.

Every ORM model in :mod:`findata.models` inherits :class:`Base`, so
``Base.metadata`` is the authoritative list of tables — Alembic autogenerate
and :func:`findata.db.session.init_db` both read it.

Two things are configured here that individual models must not override:

**Constraint naming.** ``MetaData`` carries a ``naming_convention``, so every
primary key, foreign key, unique constraint, index and check constraint gets a
deterministic name derived from its table and columns. Without this, the server
invents names for anything not named by hand — they differ between Postgres and
SQLite, and a migration cannot reliably drop or alter a constraint it cannot
name.

**Schemas.** Tables are grouped by domain (see :data:`ALL_SCHEMAS`), mirroring
``findata/sources/``. SQLite has no schemas, so
:func:`schema_translate_map_for` collapses them to the default schema there;
:func:`findata.db.session.get_engine` applies that automatically. Table names
are unique across all schemas, which makes the collapse lossless — that is a
constraint on future table names, not a happy accident.

See ``docs/DATA_MODEL.md`` for the full standard.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
#: Security master, exchanges, issuers, insiders — slowly-changing dimensions.
SCHEMA_REFERENCE = "reference"

#: Price and volume time series — append-mostly, high volume.
SCHEMA_MARKET = "market"

#: Articles, security links, transform bookkeeping — append-mostly.
SCHEMA_NEWS = "news"

#: Every schema the warehouse declares. ``alembic_version`` deliberately stays
#: in the default schema; nothing else does.
ALL_SCHEMAS: tuple[str, ...] = (SCHEMA_REFERENCE, SCHEMA_MARKET, SCHEMA_NEWS)


def schema_translate_map_for(dialect_name: str) -> dict[str, str | None]:
    """Return a SQLAlchemy ``schema_translate_map`` for *dialect_name*.

    SQLite has no concept of schemas, so every logical schema maps to ``None``
    (the default schema) and tables are rendered unqualified. Postgres needs no
    translation and gets an empty map.

    Apply it as a connection execution option — ``get_engine()`` already does::

        engine = engine.execution_options(
            schema_translate_map=schema_translate_map_for(engine.dialect.name)
        )
    """
    if dialect_name == "sqlite":
        return {schema: None for schema in ALL_SCHEMAS}
    return {}


# ---------------------------------------------------------------------------
# Constraint naming convention
# ---------------------------------------------------------------------------
# ``column_0_N_name`` joins every column in the constraint, so composite keys
# get a name describing all of them. Postgres truncates identifiers at 63
# characters, so keep composite indexes narrow.
#
# ``ck`` interpolates %(constraint_name)s, which means every CheckConstraint
# MUST be given an explicit short name — SQLAlchemy raises otherwise.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Project-wide SQLAlchemy declarative base."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
