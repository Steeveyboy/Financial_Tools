"""Guards on the schema-wide naming standard in ``docs/DATA_MODEL.md``.

These assert the *rules*, not a frozen list of names, so adding a table does not
break them — but adding one that ignores the convention does. The old schema had
three different index conventions and server-invented names for every primary and
foreign key; that is what these prevent returning.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from findata.db.base import ALL_SCHEMAS
from findata.models import Base

TABLES = sorted(Base.metadata.tables.values(), key=lambda t: t.fullname)
TABLE_IDS = [t.fullname for t in TABLES]

#: Postgres truncates identifiers beyond this, which would silently collide.
PG_IDENTIFIER_LIMIT = 63

#: Columns holding an identifier issued by an *external* body. These keep the
#: name the outside world uses, even when it ends in ``_id``, because renaming a
#: standard identifier to satisfy an internal rule loses more than it gains. The
#: rule the exception carves out of: a ``*_id`` column is one of OUR integer
#: surrogate keys, or a foreign key to one.
EXTERNAL_IDENTIFIER_COLUMNS = frozenset({"sedar_id"})


def _python_type(column):
    """Return a column's Python type, or None if it does not declare one.

    ``TypeDecorator`` subclasses (``UTCDateTime``) and some generic types raise
    ``NotImplementedError`` rather than answering.
    """
    try:
        return column.type.python_type
    except NotImplementedError:
        return None


@pytest.mark.parametrize("table", TABLES, ids=TABLE_IDS)
def test_table_is_in_a_declared_schema(table):
    """Nothing lives in the default schema; domain is expressed by schema."""
    assert table.schema in ALL_SCHEMAS, (
        f"{table.fullname} has schema={table.schema!r}; "
        f"expected one of {ALL_SCHEMAS}"
    )


@pytest.mark.parametrize("table", TABLES, ids=TABLE_IDS)
def test_table_name_is_snake_case_and_plural(table):
    assert re.fullmatch(r"[a-z][a-z0-9_]*", table.name), (
        f"{table.name} is not snake_case"
    )
    assert table.name.endswith("s"), (
        f"{table.name} is not plural — the standard requires plural table names"
    )


@pytest.mark.parametrize("table", TABLES, ids=TABLE_IDS)
def test_primary_key_follows_convention(table):
    pk = table.primary_key
    assert pk.name == f"pk_{table.name}", (
        f"{table.fullname}: primary key is named {pk.name!r}, expected "
        f"'pk_{table.name}'. An unnamed PK gets a server-invented name that "
        f"differs between backends and cannot be altered by a migration."
    )


@pytest.mark.parametrize("table", TABLES, ids=TABLE_IDS)
def test_every_constraint_and_index_is_explicitly_named(table):
    """No object may rely on the server to name it."""
    prefixes = {
        ForeignKeyConstraint: "fk_",
        UniqueConstraint: "uq_",
        CheckConstraint: "ck_",
    }
    for constraint in table.constraints:
        expected = prefixes.get(type(constraint))
        if expected is None:
            continue  # primary key — covered above
        assert constraint.name, f"{table.fullname}: unnamed {type(constraint).__name__}"
        assert str(constraint.name).startswith(expected), (
            f"{table.fullname}: {constraint.name!r} should start with {expected!r}"
        )

    for index in table.indexes:
        assert index.name.startswith("ix_"), (
            f"{table.fullname}: index {index.name!r} should start with 'ix_'"
        )


@pytest.mark.parametrize("table", TABLES, ids=TABLE_IDS)
def test_constraint_names_embed_the_table_name(table):
    """``ix_company_ticker`` on a table called ``companies`` is what this stops."""
    names = [c.name for c in table.constraints if c.name] + [
        i.name for i in table.indexes
    ]
    for name in names:
        assert table.name in name, (
            f"{table.fullname}: {name!r} does not contain the table name "
            f"{table.name!r} — the old schema mixed singular and plural here"
        )


@pytest.mark.parametrize("table", TABLES, ids=TABLE_IDS)
def test_identifier_names_fit_postgres(table):
    for name in [c.name for c in table.constraints if c.name] + [
        i.name for i in table.indexes
    ]:
        assert len(str(name)) <= PG_IDENTIFIER_LIMIT, (
            f"{table.fullname}: {name!r} is {len(str(name))} chars; Postgres "
            f"truncates at {PG_IDENTIFIER_LIMIT} and silently risks a collision"
        )


@pytest.mark.parametrize("table", TABLES, ids=TABLE_IDS)
def test_column_names_are_snake_case(table):
    for column in table.columns:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", column.name), (
            f"{table.fullname}.{column.name} is not snake_case"
        )


@pytest.mark.parametrize("table", TABLES, ids=TABLE_IDS)
def test_id_columns_are_integers(table):
    """``*_id`` is a surrogate key or an FK to one — never free text.

    ``transform_log.transform_id`` held the string ``"sentiment"``; this is the
    guard against that recurring.
    """
    for column in table.columns:
        if column.name in EXTERNAL_IDENTIFIER_COLUMNS:
            continue
        if column.name == "id" or column.name.endswith("_id"):
            assert _python_type(column) is int, (
                f"{table.fullname}.{column.name} is {column.type} — a *_id column "
                f"must be an integer key. Use a *_name column for a string."
            )


@pytest.mark.parametrize("table", TABLES, ids=TABLE_IDS)
def test_at_columns_are_timezone_aware(table):
    """Every ``*_at`` is timestamptz — mixed awareness was REPO_REVIEW #3.

    UTCDateTime is a TypeDecorator, so the flag lives on its ``impl``.
    """
    for column in table.columns:
        if not column.name.endswith("_at"):
            continue
        impl = getattr(column.type, "impl", column.type)
        aware = getattr(column.type, "timezone", False) or getattr(
            impl, "timezone", False
        )
        assert aware, f"{table.fullname}.{column.name} is not timezone-aware"


@pytest.mark.parametrize("table", TABLES, ids=TABLE_IDS)
def test_boolean_columns_are_named_is_x_and_non_null(table):
    for column in table.columns:
        if _python_type(column) is bool:
            assert column.name.startswith("is_"), (
                f"{table.fullname}.{column.name} is boolean but not named is_*"
            )
            assert not column.nullable, (
                f"{table.fullname}.{column.name} is a nullable boolean — "
                f"three-valued logic here is almost always a mistake"
            )


@pytest.mark.parametrize("table", TABLES, ids=TABLE_IDS)
def test_audit_columns_are_present(table):
    """Every table carries created_at/updated_at, with one documented exception."""
    if table.name == "article_transforms":
        # transformed_at already IS this table's write timestamp.
        assert "transformed_at" in table.columns
        return

    assert {"created_at", "updated_at"} <= set(table.columns.keys()), (
        f"{table.fullname} is missing created_at/updated_at"
    )


def test_symbol_columns_agree_on_width():
    """One symbol spelling, one width.

    Previously companies.ticker was String(20) while article_tickers.ticker and
    daily_ohlcv.ticker were String(10), so a symbol that stored in one table was
    rejected by the next.
    """
    widths = {
        f"{t.fullname}.{c.name}": c.type.length
        for t in TABLES
        for c in t.columns
        if c.name == "symbol"
    }
    assert widths, "expected at least one symbol column"
    assert len(set(widths.values())) == 1, f"symbol widths disagree: {widths}"


def test_no_column_is_named_ticker():
    """The warehouse uses `symbol`; `ticker` is the retired spelling."""
    offenders = [
        f"{t.fullname}.{c.name}"
        for t in TABLES
        for c in t.columns
        if "ticker" in c.name
    ]
    assert not offenders, f"rename to symbol: {offenders}"
