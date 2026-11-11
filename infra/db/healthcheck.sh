#!/bin/bash
# Health check for `db`. Runs over TCP: while init scripts run, the entrypoint's
# temporary server listens on the Unix socket only, so this cannot pass early.
# It then requires the marker that init.sh writes as its last step.
set -euo pipefail

pg_isready -q -h 127.0.0.1 -U "$POSTGRES_USER" -d postgres
marker=$(psql -h 127.0.0.1 -U "$POSTGRES_USER" -d postgres -tAc \
    "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = 'praxismesh'")
[ "$marker" = "praxismesh-init-complete" ]
