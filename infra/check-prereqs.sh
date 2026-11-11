#!/bin/sh
# Checks what `make up` needs and names whatever is missing (plan §8 demo:
# missing dependency gives a clear diagnostic). Exit status 1 on any problem.
set -u

env_file=${1:-infra/.env}
required="POSTGRES_PASSWORD TEMPORAL_DB_PASSWORD APP_DB_PASSWORD S3_ACCESS_KEY S3_SECRET_KEY"
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

for var in $required; do
    value=$(sed -n "s/^${var}=//p" "$env_file" | tail -n 1)
    if [ -z "$value" ]; then
        echo "error: ${var} is not set in ${env_file}" >&2
        status=1
    fi
done

model=$(sed -n 's/^VLLM_MODEL=//p' "$env_file" | tail -n 1)
case "$model" in
*/*)
    echo "error: VLLM_MODEL must not contain '/' (got '${model}')" >&2
    status=1
    ;;
esac

exit "$status"
