#!/bin/bash
# Creates PraxisMesh's roles and databases on a fresh `pgdata` volume.
#
# Run once by the postgres entrypoint, as the superuser, after ParadeDB's own
# 10_bootstrap_paradedb.sh. It never runs again on an existing volume, so a
# failed init or a changed password needs `make reset`.
#
# ParadeDB's bootstrap installs its extensions (pg_search, vector, postgis,
# pg_cron, ...) into template1. All three databases are created from template0
# instead, so Temporal's databases carry no extensions and the application
# database gets only what this script adds (ADR-0002).
#
# The last statement writes the marker the health check reads, so `db` reports
# healthy only after every step here has succeeded.
set -euo pipefail

: "${TEMPORAL_DB_PASSWORD:?TEMPORAL_DB_PASSWORD is not set}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is not set}"

psql -v ON_ERROR_STOP=1 -d postgres \
    -v temporal_pw="$TEMPORAL_DB_PASSWORD" -v app_pw="$APP_DB_PASSWORD" <<'EOSQL'
CREATE ROLE temporal LOGIN PASSWORD :'temporal_pw';
CREATE ROLE praxismesh LOGIN PASSWORD :'app_pw';

CREATE DATABASE temporal OWNER temporal TEMPLATE template0;
CREATE DATABASE temporal_visibility OWNER temporal TEMPLATE template0;
CREATE DATABASE praxismesh OWNER praxismesh TEMPLATE template0;

REVOKE CONNECT ON DATABASE temporal, temporal_visibility, praxismesh FROM PUBLIC;
GRANT CONNECT ON DATABASE temporal, temporal_visibility TO temporal;
GRANT CONNECT ON DATABASE praxismesh TO praxismesh;
EOSQL

psql -v ON_ERROR_STOP=1 -d praxismesh <<'EOSQL'
-- pg_search 0.26 requires the vector extension (pgvector).
CREATE EXTENSION IF NOT EXISTS pg_search CASCADE;
EOSQL

psql -v ON_ERROR_STOP=1 -d postgres <<'EOSQL'
COMMENT ON DATABASE praxismesh IS 'praxismesh-init-complete';
EOSQL

echo "PraxisMesh database init completed"
