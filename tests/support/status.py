"""`make status`: each service's state and health, the model endpoint, and an exit
status of 1 when any long-running service is not healthy. Run through make, which
passes infra/.env with `uv run --env-file`."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from tests.support.models import served_models

SERVICES = ("db", "temporal", "temporal-ui", "s3")
COMPOSE = ("docker", "compose")
PS = ("ps", "-a", "--format", "json")


def compose_ps() -> list[dict[str, str]]:
    env_file = os.environ.get("ENV_FILE", "infra/.env")
    out = subprocess.run(
        [*COMPOSE, "--env-file", env_file, "-f", "infra/docker-compose.yml", *PS],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    # Compose prints one JSON object per line.
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def main() -> int:
    rows = {row["Service"]: row for row in compose_ps()}
    for service in sorted(rows):
        print(f"{service:20} {rows[service]['Status']}")
    print(
        f"addresses: Temporal 127.0.0.1:{os.environ['TEMPORAL_PORT']}, "
        f"UI http://127.0.0.1:{os.environ['TEMPORAL_UI_PORT']}, "
        f"S3 http://127.0.0.1:{os.environ['S3_PORT']}, DB 127.0.0.1:{os.environ['DB_PORT']}"
    )

    base_url = os.environ.get("VLLM_BASE_URL", "")
    if not base_url:
        print("model endpoint: not configured (VLLM_BASE_URL is empty)")
    else:
        try:
            served_models(base_url, os.environ.get("VLLM_API_KEY", ""))
            print(f"model endpoint: {base_url} answers /v1/models")
        except Exception as e:  # report any failure; status itself must not crash
            print(f"model endpoint: {base_url} is unreachable or failing: {e}")

    bad = [s for s in SERVICES if rows.get(s, {}).get("Health") != "healthy"]
    if bad:
        print(f"unhealthy or stopped: {' '.join(bad)}")
        return 1
    print("all services healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
