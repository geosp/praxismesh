"""A scratch application database, created by the superuser on the stack's
database server, so tests of whole-database checks and migrations never touch
the stack's own `praxismesh` database."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from common.persistence.settings import app_database_url

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "common" / "persistence" / "alembic.ini"


def superuser_url(database: str = "postgres") -> URL:
    return app_database_url(user="postgres", database=database, password_var="POSTGRES_PASSWORD")


async def migrate(database: str, target: str, *, down: bool = False) -> None:
    config = Config(str(ALEMBIC_INI))
    config.attributes["database"] = database
    step = command.downgrade if down else command.upgrade
    # env.py runs its own event loop, so it runs in a thread.
    await asyncio.to_thread(step, config, target)


@asynccontextmanager
async def scratch_database(target: str | None = None) -> AsyncIterator[tuple[str, AsyncEngine]]:
    """Create a database owned by the app role, with pg_search, migrated to
    `target` if given; yield its name and an app-role engine; drop it after."""
    name = f"praxis_scratch_{uuid.uuid4().hex[:10]}"
    admin = create_async_engine(superuser_url(), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f"CREATE DATABASE {name} OWNER praxismesh TEMPLATE template0"))
    db_admin = create_async_engine(superuser_url(name))
    async with db_admin.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search CASCADE"))
    await db_admin.dispose()
    engine = create_async_engine(app_database_url(database=name))
    try:
        if target is not None:
            await migrate(name, target)
        yield name, engine
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
        await admin.dispose()
