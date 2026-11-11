#!/bin/sh
# Checks what `make up` needs and names whatever is missing or invalid.
# Exit status 1 on any problem.
#
# infra/.env is read by Make (include), by Docker Compose (--env-file) and by
# this script. They agree only on plain KEY=value lines, so that is the only
# syntax accepted: no quotes, spaces, '#', '$', '\' or '`' in values.
set -u

env_file=${1:-infra/.env}
required="POSTGRES_PASSWORD TEMPORAL_DB_PASSWORD APP_DB_PASSWORD S3_ACCESS_KEY S3_SECRET_KEY"
required="$required DB_PORT TEMPORAL_PORT TEMPORAL_UI_PORT TEMPORAL_NAMESPACE TEMPORAL_RETENTION"
required="$required S3_PORT VLLM_MODEL"
status=0

if ! command -v docker >/dev/null 2>&1; then
    echo "error: docker is not installed or not on PATH" >&2
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "error: Docker is not running (docker info failed); start the Docker daemon" >&2
    status=1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "error: the Docker Compose plugin is missing (docker compose version failed)" >&2
    status=1
fi

if [ ! -f "$env_file" ]; then
    echo "error: ${env_file} is missing; create it with: cp infra/.env.example ${env_file}" >&2
    exit 1
fi

# Every non-comment line must be KEY=value with a plain value.
bad=$(grep -nvE '^[[:space:]]*(#.*)?$|^[A-Z][A-Z0-9_]*=[^[:space:]"'"'"'#$\\`]*$' "$env_file")
if [ -n "$bad" ]; then
    echo "$bad" | while IFS= read -r line; do
        echo "error: ${env_file} line ${line%%:*}: use KEY=value with no quotes, spaces, '#', '\$', '\\' or '\`' in the value" >&2
    done
    status=1
fi

value() {
    sed -n "s/^$1=//p" "$env_file" | tail -n 1
}

for var in $required; do
    if [ -z "$(value "$var")" ]; then
        echo "error: ${var} is not set in ${env_file}" >&2
        status=1
    fi
done

case "$(value VLLM_MODEL)" in
*/*)
    echo "error: VLLM_MODEL must not contain '/' (got '$(value VLLM_MODEL)')" >&2
    status=1
    ;;
esac

retention=$(value TEMPORAL_RETENTION)
if [ -n "$retention" ] && ! echo "$retention" | grep -qE '^[1-9][0-9]*[smhd]$'; then
    echo "error: TEMPORAL_RETENTION must be <number><s|m|h|d>, for example 72h (got '${retention}')" >&2
    status=1
fi

exit "$status"
