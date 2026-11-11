#!/bin/sh
# Checks what the stack needs and names whatever is missing or invalid.
#
#     sh infra/check-prereqs.sh [ENV_FILE]                  full check; exit 1 on any problem
#     sh infra/check-prereqs.sh --project-only [ENV_FILE]   print the Compose project name
#
# infra/.env is read by Docker Compose (--env-file), by `uv run --env-file` (tests,
# migrations) and by a shell in the README's examples. They agree only on plain
# lines, so this accepts nothing else: comments, blank lines, and KEY=value where
# KEY is a known variable and the value uses only A-Z a-z 0-9 . _ : / @ % + , = -
set -u

project_only=0
if [ "${1:-}" = "--project-only" ]; then
    project_only=1
    shift
fi
env_file=${1:-infra/.env}

known="COMPOSE_PROJECT_NAME POSTGRES_PASSWORD TEMPORAL_DB_PASSWORD APP_DB_PASSWORD DB_PORT"
known="$known TEMPORAL_PORT TEMPORAL_UI_PORT TEMPORAL_NAMESPACE TEMPORAL_RETENTION"
known="$known S3_PORT S3_ACCESS_KEY S3_SECRET_KEY VLLM_BASE_URL VLLM_MODEL VLLM_API_KEY"
# Everything except the model endpoint and its key must be non-empty.
required=$(printf '%s\n' "$known" | tr ' ' '\n' | grep -vE '^VLLM_(BASE_URL|API_KEY)$' | tr '\n' ' ')

value() {
    sed -n "s/^$1=//p" "$env_file" | tail -n 1
}

# A Compose project name: what Compose accepts (lowercase), never empty.
project_name() {
    name=${COMPOSE_PROJECT_NAME:-}
    [ -n "$name" ] || { [ -f "$env_file" ] && name=$(value COMPOSE_PROJECT_NAME); }
    if [ -z "$name" ]; then
        echo "error: COMPOSE_PROJECT_NAME is not set (in ${env_file} or the shell); refusing to guess which stack to act on" >&2
        return 1
    fi
    if ! printf '%s\n' "$name" | grep -qE '^[a-z0-9][a-z0-9_-]*$'; then
        echo "error: COMPOSE_PROJECT_NAME '${name}' must be lowercase letters, digits, '_' or '-'" >&2
        return 1
    fi
    printf '%s\n' "$name"
}

if [ "$project_only" = 1 ]; then
    project_name
    exit $?
fi

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

n=0
while IFS= read -r line || [ -n "$line" ]; do
    n=$((n + 1))
    case "$line" in
    *\\) echo "error: ${env_file} line ${n}: a line must not end with '\\'" >&2; status=1; continue ;;
    '' | '#'*) continue ;;
    esac
    key=${line%%=*}
    if [ "$key" = "$line" ] || ! printf '%s\n' "$known" | tr ' ' '\n' | grep -qxF "$key"; then
        echo "error: ${env_file} line ${n}: expected KEY=value with a known KEY (see infra/.env.example)" >&2
        status=1
    elif ! printf '%s\n' "${line#*=}" | grep -qE '^[A-Za-z0-9._:/@%+,=-]*$'; then
        echo "error: ${env_file} line ${n}: ${key}'s value may use only A-Z a-z 0-9 . _ : / @ % + , = -" >&2
        status=1
    fi
done <"$env_file"

for var in $required; do
    if [ -z "$(value "$var")" ]; then
        echo "error: ${var} is not set in ${env_file}" >&2
        status=1
    fi
done

project_name >/dev/null || status=1

case "$(value VLLM_MODEL)" in
*/*)
    echo "error: VLLM_MODEL must not contain '/' (got '$(value VLLM_MODEL)')" >&2
    status=1
    ;;
esac

# Temporal rejects retention under one day; up to 5 digits avoids overflow.
retention=$(value TEMPORAL_RETENTION)
if [ -n "$retention" ]; then
    if ! printf '%s\n' "$retention" | grep -qE '^[1-9][0-9]{0,4}[smhd]$'; then
        echo "error: TEMPORAL_RETENTION must be <number><s|m|h|d>, for example 72h (got '${retention}')" >&2
        status=1
    else
        num=${retention%?}
        case "$retention" in
        *s) secs=$num ;; *m) secs=$((num * 60)) ;; *h) secs=$((num * 3600)) ;; *d) secs=$((num * 86400)) ;;
        esac
        if [ "$secs" -lt 86400 ]; then
            echo "error: TEMPORAL_RETENTION must be at least one day (24h or 1d); got '${retention}'" >&2
            status=1
        fi
    fi
fi

exit "$status"
