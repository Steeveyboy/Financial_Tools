"""
Shared declarative base for all ORM models.

All models in this package must inherit from :class:`Base` so that
Alembic can discover them automatically and so that
:func:`findata.db.session.init_db` can create all tables in one call.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide SQLAlchemy declarative base."""
    pass
