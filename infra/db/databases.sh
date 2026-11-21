#!/bin/bash
# Creates PraxisMesh's three databases with their CONNECT grants and the
# application database's extensions. The roles `temporal` and `praxismesh` must
# exist (init.sh creates them).
#
# Run as the database superuser: by init.sh on a fresh `pgdata` volume, and by
# infra/restore.sh after it drops the databases (Phase 3A persistence plan D8,
# notes.md#d8). Safe to run again: it creates only what is missing. With
# --no-extensions it leaves the application database without them: a restore
# loads them from its dump, which also creates the `paradedb` schema.
#
# ParadeDB's bootstrap installs its extensions (pg_search, vector, postgis, ...)
# into template1 and its own `paradedb` database, and pg_cron into `postgres`.
# All three databases are created from template0 instead, so Temporal's
# databases carry no extensions and the application database gets only what
# this script adds (ADR-0002).
set -euo pipefail

psql -v ON_ERROR_STOP=1 -d postgres <<'EOSQL'
SELECT format('CREATE DATABASE %I OWNER %I TEMPLATE template0', d, o)
FROM (VALUES ('temporal', 'temporal'), ('temporal_visibility', 'temporal'),
             ('praxismesh', 'praxismesh')) AS want(d, o)
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = d) \gexec

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_database WHERE datname = 'paradedb') THEN
    REVOKE CONNECT ON DATABASE paradedb FROM PUBLIC;
  END IF;
END $$;
REVOKE CONNECT ON DATABASE postgres, temporal, temporal_visibility, praxismesh FROM PUBLIC;
GRANT CONNECT ON DATABASE temporal, temporal_visibility TO temporal;
GRANT CONNECT ON DATABASE praxismesh TO praxismesh;
EOSQL

if [ "${1:-}" = "--no-extensions" ]; then
    echo "PraxisMesh databases ready (no extensions)"
    exit 0
fi

psql -v ON_ERROR_STOP=1 -d praxismesh <<'EOSQL'
-- pg_search 0.26 requires the vector extension (pgvector).
CREATE EXTENSION IF NOT EXISTS pg_search CASCADE;
EOSQL

echo "PraxisMesh databases ready"
