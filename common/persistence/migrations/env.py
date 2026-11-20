"""Alembic environment for the application database (async, SQLAlchemy with asyncpg).

Migrations run as the application role against the `praxismesh` database only;
Temporal's databases are private to Temporal (plan §4.16). Tests may name a
scratch database through `config.attributes["database"]` or `-x database=NAME`.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import URL, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from common.persistence.settings import APP_DB_NAME, app_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _url() -> URL:
    named = context.get_x_argument(as_dictionary=True).get("database", APP_DB_NAME)
    database = config.attributes.get("database") or named
    return app_database_url(database=database)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a database connection."""
    context.configure(
        url=_url().render_as_string(hide_password=True),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
