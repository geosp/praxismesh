#!/bin/bash
# Creates PraxisMesh's roles and databases on a fresh `pgdata` volume.
#
# Run once by the postgres entrypoint, as the superuser, after ParadeDB's own
# 10_bootstrap_paradedb.sh. It never runs again on an existing volume, so a
# failed init or a changed password needs `make reset`.
#
# The databases, their CONNECT grants and extensions are in databases.sh
# (mounted as praxismesh-databases), which infra/restore.sh runs again after it
# drops them (Phase 3A persistence plan D8).
#
# The last statement writes the marker the health check reads, so `db` reports
# healthy only after every step here has succeeded. The marker is a comment on
# database `postgres`, which only the superuser can change.
set -euo pipefail

: "${TEMPORAL_DB_PASSWORD:?TEMPORAL_DB_PASSWORD is not set}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is not set}"

psql -v ON_ERROR_STOP=1 -d postgres \
    -v temporal_pw="$TEMPORAL_DB_PASSWORD" -v app_pw="$APP_DB_PASSWORD" <<'EOSQL'
CREATE ROLE temporal LOGIN PASSWORD :'temporal_pw';
CREATE ROLE praxismesh LOGIN PASSWORD :'app_pw';
EOSQL

bash /usr/local/bin/praxismesh-databases

# The comms role (Phase 2 messaging D13), before the marker, so a healthy `db`
# already has it when migration 0006 grants it the message tables.
bash /usr/local/bin/praxismesh-roles

psql -v ON_ERROR_STOP=1 -d postgres <<'EOSQL'
COMMENT ON DATABASE postgres IS 'praxismesh-init-complete';
EOSQL

echo "PraxisMesh database init completed"
