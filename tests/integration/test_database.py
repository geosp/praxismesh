"""Application database: separation from Temporal, pg_search, migrations at head."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import URL, exc, text
from sqlalchemy.ext.asyncio import create_async_engine

from common.persistence.settings import app_database_url

pytestmark = pytest.mark.integration

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "common" / "persistence" / "alembic.ini"
TEMPORAL_ROLE = {"user": "temporal", "password_var": "TEMPORAL_DB_PASSWORD"}


async def scalar(sql: str, url: URL | None = None) -> object:
    url = url or app_database_url()
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text(sql))).scalar()
    except OSError as e:
        raise RuntimeError(
            f"database server (service db) at {url.host}:{url.port} is unreachable; "
            f"check make status: {e}"
        ) from e
    finally:
        await engine.dispose()


@pytest.mark.parametrize("database", ["temporal", "temporal_visibility", "postgres"])
async def test_app_role_refused_elsewhere(database: str) -> None:
    with pytest.raises(exc.DBAPIError, match="permission denied for database"):
        await scalar("SELECT 1", app_database_url(database=database))


@pytest.mark.parametrize("database", ["praxismesh", "postgres"])
async def test_temporal_role_refused_elsewhere(database: str) -> None:
    with pytest.raises(exc.DBAPIError, match="permission denied for database"):
        await scalar("SELECT 1", app_database_url(database=database, **TEMPORAL_ROLE))


async def test_pg_search_installed() -> None:
    assert await scalar("SELECT 1 FROM pg_extension WHERE extname = 'pg_search'") == 1


async def test_migrations_at_head() -> None:
    head = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_current_head()
    table = await scalar("SELECT to_regclass('public.alembic_version')::text")
    assert table is not None, "no migrations applied to the praxismesh database; run make migrate"
    assert await scalar("SELECT version_num FROM alembic_version") == head
