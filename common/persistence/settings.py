"""Connection settings for the application database, read from the environment.

`make migrate` and `make smoke` export `infra/.env` into the environment; see
`infra/.env.example` for the variables.
"""

from __future__ import annotations

import os

from sqlalchemy import URL

APP_DB_NAME = "praxismesh"
APP_DB_USER = "praxismesh"


def app_database_url(
    *, user: str = APP_DB_USER, database: str = APP_DB_NAME, password_var: str = "APP_DB_PASSWORD"
) -> URL:
    """Return the asyncpg URL for a database on the local stack.

    Defaults to the application role and database. Tests pass another role and
    its password variable (for example `temporal`, `TEMPORAL_DB_PASSWORD`).
    """
    password = os.environ.get(password_var, "")
    if not password:
        raise RuntimeError(f"{password_var} is not set; run through make, which loads infra/.env")
    return URL.create(
        "postgresql+asyncpg",
        username=user,
        password=password,
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database=database,
    )
