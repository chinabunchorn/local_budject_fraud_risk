"""Alembic environment — URL comes from DATABASE_URL, never from alembic.ini."""

import os

from alembic import context
from sqlalchemy import create_engine


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Example: "
            "postgresql+psycopg://mission3:...@localhost:5432/mission3"
        )
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a database connection (--sql mode)."""
    context.configure(url=_database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url())
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
