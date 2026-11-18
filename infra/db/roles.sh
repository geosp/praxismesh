#!/bin/bash
# Creates the `praxis_comms` role that comms_mcp connects as (Phase 2 messaging
# D13), with only CONNECT on the application database and USAGE on its schema.
# Table grants come from migration 0006. Safe to run again: it creates the role
# only if missing and resets its password.
#
# Run as the database superuser: by init.sh on a fresh `pgdata` volume, and by
# `make db-roles` on an existing one. Without PRAXIS_COMMS_DB_PASSWORD it does
# nothing, so a stack without comms still starts.
set -euo pipefail

if [ -z "${PRAXIS_COMMS_DB_PASSWORD:-}" ]; then
    echo "PRAXIS_COMMS_DB_PASSWORD is not set; skipping the praxis_comms role"
    exit 0
fi

psql -v ON_ERROR_STOP=1 -d postgres -v comms_pw="$PRAXIS_COMMS_DB_PASSWORD" <<'EOSQL'
SELECT format('CREATE ROLE praxis_comms LOGIN PASSWORD %L', :'comms_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'praxis_comms') \gexec
ALTER ROLE praxis_comms LOGIN PASSWORD :'comms_pw';
GRANT CONNECT ON DATABASE praxismesh TO praxis_comms;
EOSQL

# The table grants of migration 0006, again, for a role created after it ran.
psql -v ON_ERROR_STOP=1 -d praxismesh <<'EOSQL'
GRANT USAGE ON SCHEMA public TO praxis_comms;
DO $$ BEGIN
    IF to_regclass('public.task_messages') IS NOT NULL THEN
        GRANT SELECT, INSERT, UPDATE ON task_messages TO praxis_comms;
        GRANT SELECT ON task_inbox, tasks, task_attempts TO praxis_comms;
        GRANT INSERT ON message_wakes TO praxis_comms;
    END IF;
END $$;
EOSQL

echo "praxis_comms role ready"
