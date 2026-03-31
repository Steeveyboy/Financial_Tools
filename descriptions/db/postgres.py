"""Reusable PostgreSQL client built on SQLAlchemy.

Usage:
    from descriptions.db.postgres import PostgresClient

    client = PostgresClient(connection_string="postgresql://...")
    client.create_tables()           # idempotent DDL
    client.upsert(MyModel, data)     # insert-or-update helper
    client.close()

Or as a context manager:
    with PostgresClient(connection_string="...") as client:
        client.create_tables()
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator, Sequence, Type

from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from descriptions.db.models import Base

logger = logging.getLogger(__name__)


class PostgresClient:
    """Thin wrapper around a SQLAlchemy engine + session factory.

    Parameters
    ----------
    connection_string : str
        A SQLAlchemy-compatible PostgreSQL URI.
    schema : str
        The database schema to operate in (default ``"public"``).
    echo : bool
        If *True*, log all SQL statements (useful for debugging).
    """

    def __init__(
        self,
        connection_string: str,
        schema: str = "public",
        echo: bool = False,
    ) -> None:
        self._connection_string = connection_string
        self.schema = schema
        self._engine: Engine = create_engine(
            connection_string,
            echo=echo,
            pool_pre_ping=True,
        )
        self._session_factory = sessionmaker(bind=self._engine)

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------
    def __enter__(self) -> "PostgresClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        self.close()

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------
    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Yield a transactional session that auto-commits / rolls back."""
        sess = self._session_factory()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

    # ------------------------------------------------------------------
    # DDL
    # ------------------------------------------------------------------
    def create_tables(self) -> None:
        """Create all tables defined in *models.py* (idempotent)."""
        if self.schema != "public":
            with self._engine.connect() as conn:
                conn.execute(
                    text(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
                )
                conn.commit()
        Base.metadata.create_all(self._engine)
        logger.info("Tables created / verified.")

    def drop_tables(self) -> None:
        """Drop all managed tables.  **Destructive** — use with care."""
        Base.metadata.drop_all(self._engine)
        logger.info("Tables dropped.")

    # ------------------------------------------------------------------
    # Generic CRUD helpers
    # ------------------------------------------------------------------
    def upsert(
        self,
        model: Type[Base],
        records: Sequence[dict[str, Any]],
        conflict_column: str = "id",
        batch_size: int = 500,
    ) -> int:
        """Insert rows; on conflict update all non-PK columns.

        Uses PostgreSQL ``INSERT … ON CONFLICT … DO UPDATE``.

        Parameters
        ----------
        model : SQLAlchemy declarative model class
        records : list of dicts whose keys match column names
        conflict_column : the unique column to detect conflicts on
        batch_size : commit every *batch_size* rows

        Returns
        -------
        int : total number of rows upserted
        """
        if not records:
            return 0
        table = model.__table__
        total = 0
        with self._engine.begin() as conn:
            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]
                stmt = pg_insert(table).values(batch)
                update_cols = {
                    c.name: stmt.excluded[c.name]
                    for c in table.columns
                    if c.name != conflict_column and not c.primary_key
                }
                if update_cols:
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[conflict_column],
                        set_=update_cols,
                    )
                else:
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=[conflict_column],
                    )
                conn.execute(stmt)
                total += len(batch)
        logger.info("Upserted %d rows into %s.", total, table.name)
        return total

    def bulk_insert(
        self,
        model: Type[Base],
        records: Sequence[dict[str, Any]],
        batch_size: int = 500,
    ) -> int:
        """Plain bulk insert (no conflict handling).

        Parameters
        ----------
        model : SQLAlchemy declarative model class
        records : list of dicts
        batch_size : commit every *batch_size* rows

        Returns
        -------
        int : total rows inserted
        """
        if not records:
            return 0
        total = 0
        with self.session() as sess:
            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]
                sess.bulk_insert_mappings(model, batch)
                sess.flush()
                total += len(batch)
        logger.info("Inserted %d rows into %s.", total, model.__tablename__)
        return total

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        """Execute raw SQL and return the result proxy."""
        with self._engine.begin() as conn:
            return conn.execute(text(sql), params or {})

    def count(self, model: Type[Base]) -> int:
        """Return the row count for a table."""
        with self.session() as sess:
            return sess.query(model).count()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Dispose of the engine and release all pooled connections."""
        self._engine.dispose()
        logger.info("PostgresClient connection disposed.")
