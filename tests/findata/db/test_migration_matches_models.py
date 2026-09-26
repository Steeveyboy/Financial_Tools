"""``alembic upgrade head`` must produce exactly what the models describe.

Why this exists rather than ``alembic check``: the models declare Postgres
schemas and SQLite has none, so the engine applies a ``schema_translate_map``.
Autogenerate compares ``Base.metadata`` (schema='news') against SQLite
reflection (schema=None) and reports every table as both added and removed, so
``alembic check`` is only meaningful against Postgres. This builds the schema
both ways on SQLite and compares the results instead.

It earned its place immediately: it caught the baseline migration using
``sa.text("now()")`` for timestamp defaults, which SQLite emits verbatim as
``DEFAULT (now())`` — a function it does not have — so every INSERT would have
failed. ``sa.func.now()`` compiles per dialect.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from findata.db.base import schema_translate_map_for
from findata.models import Base

REPO_ROOT = Path(__file__).resolve().parents[3]

#: SQLite's FTS5 shadow tables are implementation detail of the virtual table
#: and are not created identically by both paths.
_FTS_PREFIX = "companies_fts"


def _objects(db_path: Path) -> dict[tuple[str, str], str]:
    """Return ``{(type, name): normalised SQL}`` for a SQLite database."""
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
        ).fetchall()
    finally:
        connection.close()
    return {
        (kind, name): " ".join((sql or "").split())
        for kind, name, sql in rows
        if not name.startswith(_FTS_PREFIX)
    }


def _clauses(sql: str) -> list[str]:
    """Split a CREATE TABLE body into its top-level clauses, order-independent.

    Both paths emit the same columns and constraints but not in the same order,
    which is semantically irrelevant.
    """
    body = sql[sql.index("(") + 1 : sql.rindex(")")]
    parts, depth, current = [], 0, ""
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char
    parts.append(current.strip())
    return sorted(p.replace('"', "") for p in parts if p)


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory) -> Path:
    """A database built by ``alembic upgrade head``."""
    path = tmp_path_factory.mktemp("alembic") / "migrated.db"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={"DATABASE_URL": f"sqlite:///{path}", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"
    )
    return path


@pytest.fixture(scope="module")
def model_db(tmp_path_factory) -> Path:
    """A database built by ``Base.metadata.create_all()``."""
    path = tmp_path_factory.mktemp("models") / "models.db"
    engine = create_engine(f"sqlite:///{path}").execution_options(
        schema_translate_map=schema_translate_map_for("sqlite")
    )
    Base.metadata.create_all(engine)
    engine.dispose()
    return path


def test_same_objects_exist(migrated_db, model_db):
    from_models, from_migration = _objects(model_db), _objects(migrated_db)

    missing = sorted(set(from_models) - set(from_migration))
    extra = sorted(set(from_migration) - set(from_models))

    assert not missing, f"the migration does not create: {missing}"
    assert not extra, f"the migration creates objects no model declares: {extra}"


def test_table_definitions_match(migrated_db, model_db):
    from_models, from_migration = _objects(model_db), _objects(migrated_db)

    mismatches = {}
    for key in sorted(set(from_models) & set(from_migration)):
        if key[0] != "table":
            continue
        model_clauses = _clauses(from_models[key])
        migration_clauses = _clauses(from_migration[key])
        if model_clauses != migration_clauses:
            mismatches[key[1]] = {
                "only_in_models": sorted(set(model_clauses) - set(migration_clauses)),
                "only_in_migration": sorted(
                    set(migration_clauses) - set(model_clauses)
                ),
            }

    assert not mismatches, f"migration and models disagree: {mismatches}"


def test_index_definitions_match(migrated_db, model_db):
    from_models, from_migration = _objects(model_db), _objects(migrated_db)

    for key in sorted(set(from_models) & set(from_migration)):
        if key[0] != "index":
            continue
        assert from_models[key].replace('"', "") == from_migration[key].replace(
            '"', ""
        ), f"index {key[1]} differs between models and migration"


def test_inserts_work_against_the_migrated_schema(migrated_db):
    """Guards the sa.text("now()") class of bug: DDL that only fails on write."""
    from sqlalchemy import text

    engine = create_engine(f"sqlite:///{migrated_db}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO articles (url, ingest_source, published_at) "
                "VALUES ('https://example.com/migration-probe', 'test', "
                "'2026-01-02 09:30:00+00:00')"
            )
        )
        row = connection.execute(
            text(
                "SELECT created_at, updated_at FROM articles "
                "WHERE url = 'https://example.com/migration-probe'"
            )
        ).one()
    engine.dispose()

    assert row[0] is not None, "created_at server_default did not fire"
    assert row[1] is not None, "updated_at server_default did not fire"
