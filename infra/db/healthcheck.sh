#!/bin/bash
# Health check for `db`. Runs over TCP: while init scripts run, the entrypoint's
# temporary server listens on the Unix socket only, so this cannot pass early.
# It then requires the marker that init.sh writes as its last step (a comment on
# database `postgres`, which only the superuser can change).
set -euo pipefail

psql_super() {
    psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U "$POSTGRES_USER" -tA "$@"
}

pg_isready -q -h 127.0.0.1 -U "$POSTGRES_USER" -d postgres

marker=$(psql_super -d postgres -c \
    "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = 'postgres'")
[ "$marker" = "praxismesh-init-complete" ] && exit 0

# Upgrade, once, a volume initialised before the marker moved to `postgres`
# (PR #38) or before CONNECT on `paradedb` was revoked (PR #40). Such a volume
# finished init if `praxismesh` has both `vector` and `pg_search`: init creates
# them together as its last step before the marker, and `vector` can only be
# created by the superuser, so the application role cannot fake this. A fresh
# volume whose init failed has neither, and stays unhealthy.
has_db=$(psql_super -d postgres -c "SELECT count(*) FROM pg_database WHERE datname = 'praxismesh'")
[ "$has_db" = 1 ] || exit 1
extensions=$(psql_super -d praxismesh -c \
    "SELECT count(*) FROM pg_extension WHERE extname IN ('vector', 'pg_search')")
[ "$extensions" = 2 ] || exit 1

psql_super -d postgres >/dev/null <<'EOSQL'
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_database WHERE datname = 'paradedb') THEN
    REVOKE CONNECT ON DATABASE paradedb FROM PUBLIC;
  END IF;
END $$;
REVOKE CONNECT ON DATABASE postgres, temporal, temporal_visibility, praxismesh FROM PUBLIC;
COMMENT ON DATABASE praxismesh IS NULL;
COMMENT ON DATABASE postgres IS 'praxismesh-init-complete';
EOSQL
echo "upgraded an existing PraxisMesh volume (init marker and CONNECT revokes)"
