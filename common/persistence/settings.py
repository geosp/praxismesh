"""Connection settings for the application database, read from the environment.

`make migrate` and `make smoke` export `infra/.env` into the environment; see
`infra/.env.example` for the variables.
"""

from __future__ import annotations

import os

from sqlalchemy import URL

APP_DB_NAME = "praxismesh"
APP_DB_USER = "praxismesh"


def app_database_url(*, user: str = APP_DB_USER, database: str = APP_DB_NAME) -> URL:
    """Return the asyncpg URL for the application database on the local stack."""
    password = os.environ.get("APP_DB_PASSWORD", "")
    if not password:
        raise RuntimeError("APP_DB_PASSWORD is not set; run through make, which loads infra/.env")
    return URL.create(
        "postgresql+asyncpg",
        username=user,
        password=password,
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database=database,
    )
