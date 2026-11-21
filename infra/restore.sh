#!/bin/bash
# Restores a `make backup` into this checkout's stack (Phase 3A persistence plan
# R16, R23, D8; notes.md#d8). Run through `make restore BACKUP=backups/<time>`,
# which sets PROJECT_NAME (from the env file only) and ENV_FILE.
#
#  1. Refuse unless the backup is complete and fits this checkout (its manifest,
#     format, migration head, and every dump and object at its size), no
#     earlier restore was left unfinished, and the stack holds no data: no row
#     in an application table, no Workflow in the app's namespace (asked
#     through Temporal's API) and no bucket objects (R23).
#  2. Mark the restore as started, then stop the workers and Temporal.
#  3. Drop praxismesh, temporal and temporal_visibility, recreate them with
#     databases.sh and roles.sh, so the grants return, and pg_restore each dump.
#  4. Load the bucket objects, start Temporal and the workers that were
#     running, clear the mark, and print `agentctl reconcile`'s report. Its
#     findings are information: restore does not fail on them.
#
# A restore stopped after step 2 leaves its mark, so the next one refuses: run
# `make reset` and `make up`, then restore again.
set -euo pipefail

backup=${1:-}
: "${PROJECT_NAME:?run this through 'make restore BACKUP=...'}"
: "${ENV_FILE:?run this through 'make restore BACKUP=...'}"
DATABASES="praxismesh temporal temporal_visibility"
WORKERS="orchestrator worker-a worker-b worker-dsh-a worker-dsh-b"
MARK=praxismesh-restore-in-progress

die() { echo "restore: $*" >&2; exit 1; }
compose() { docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f infra/docker-compose.yml "$@"; }
uv_run() { uv run --env-file "$ENV_FILE" "$@"; }

[ -n "$backup" ] || die "usage: make restore BACKUP=backups/<time>"
# The manifest whole, this checkout's format and migration head, and every
# dump and object at its size (impl-review F179).
uv_run python -m orchestrator.backup check-backup "$backup" || exit 1

psql_super() { compose exec -T -u postgres db psql -v ON_ERROR_STOP=1 -X -q -tA "$@"; }

# 1. Refusals. The mark is a comment on the superuser role, which only the
# superuser can change; the init marker (on database `postgres`) is untouched.
mark=$(psql_super -d postgres -c \
    "SELECT shobj_description(oid, 'pg_authid') FROM pg_roles WHERE rolname = 'postgres'")
if [ "$mark" = "$MARK" ]; then
    die "an earlier restore did not finish. Run 'make reset' and 'make up' (this deletes the stack's data), then restore again"
fi
uv_run python -m orchestrator.backup check-empty || exit 1

# 2. From here a stop leaves the mark.
psql_super -d postgres -c "COMMENT ON ROLE postgres IS '$MARK'"
running=$(compose ps --services --status running)
restart=""
for w in $WORKERS; do
    if printf '%s\n' "$running" | grep -qx "$w"; then restart="$restart $w"; fi
done
echo "restore: stopping the workers and Temporal"
# shellcheck disable=SC2086 # word splitting intended
compose stop $restart temporal-ui temporal >/dev/null

# 3. The databases, recreated with their grants, then loaded.
for db in $DATABASES; do
    psql_super -d postgres -c "DROP DATABASE IF EXISTS $db WITH (FORCE)"
done
compose exec -T -u postgres db bash /usr/local/bin/praxismesh-databases --no-extensions
compose exec -T -u postgres db bash /usr/local/bin/praxismesh-roles
for db in $DATABASES; do
    echo "restore: loading $db"
    compose exec -T -u postgres db pg_restore --exit-on-error -d "$db" <"$backup/$db.dump"
done
# The comms role's table grants come with the dump; set them again in case it
# was taken before the role existed.
compose exec -T -u postgres db bash /usr/local/bin/praxismesh-roles >/dev/null

# 4. The bucket, then Temporal and the workers.
uv_run python -m orchestrator.backup load-blobs "$backup"
compose up -d --no-deps --wait --wait-timeout 180 temporal temporal-ui
if [ -n "$restart" ]; then
    # shellcheck disable=SC2086
    compose start $restart
fi
psql_super -d postgres -c "COMMENT ON ROLE postgres IS NULL"
echo "restore: done; reconcile's report follows"
uv_run python -m orchestrator.cli reconcile ||
    echo "restore: reconcile listed the findings above (information only; restore succeeded)"
