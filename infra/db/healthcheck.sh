#!/bin/bash
# Health check for `db`. Runs over TCP: while init scripts run, the entrypoint's
# temporary server listens on the Unix socket only, so this cannot pass early.
# It then requires the marker that init.sh writes as its last step (a comment on
# database `postgres`, which only the superuser can change).
set -euo pipefail

# Volumes initialised before the marker moved (075791a and earlier) carry it on
# database `praxismesh`; accept that too, so an upgrade never needs a reset.
pg_isready -q -h 127.0.0.1 -U "$POSTGRES_USER" -d postgres
found=$(psql -h 127.0.0.1 -U "$POSTGRES_USER" -d postgres -tAc \
    "SELECT count(*) FROM pg_database
     WHERE datname IN ('postgres', 'praxismesh')
       AND shobj_description(oid, 'pg_database') = 'praxismesh-init-complete'")
[ "$found" -ge 1 ]
