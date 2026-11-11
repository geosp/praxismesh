"""`make unhealthy-check`: a stopped database is reported by name (local-stack spec,
Unhealthy service).

    stop db -> `make status` exits non-zero naming db
    -> the database smoke test fails naming the database -> start db, make up

Run through make, which loads infra/.env: make unhealthy-check
"""

from __future__ import annotations

import os
import subprocess
import sys

COMPOSE = [
    "docker",
    "compose",
    "-p",
    os.environ.get("COMPOSE_PROJECT_NAME", "praxismesh"),
    "--env-file",
    os.environ.get("ENV_FILE", "infra/.env"),
    "-f",
    "infra/docker-compose.yml",
]


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def main() -> int:
    failures: list[str] = []
    print("unhealthy-check: stopping db", flush=True)
    run([*COMPOSE, "stop", "db"]).check_returncode()
    try:
        status = run(["make", "--no-print-directory", "status"])
        if status.returncode == 0 or "unhealthy or stopped: db" not in status.stdout:
            failures.append(f"make status did not name db (exit {status.returncode})")

        smoke = run(
            [
                "uv",
                "run",
                "pytest",
                "-m",
                "integration",
                "tests/integration/test_database.py::test_pg_search_installed",
            ]
        )
        if smoke.returncode == 0:
            failures.append("the database smoke test passed with db stopped")
        elif "database server (service db)" not in smoke.stdout:
            failures.append("the database smoke test failed without naming the database")
    finally:
        print("unhealthy-check: starting db", flush=True)
        run([*COMPOSE, "start", "db"])
        subprocess.run(["make", "--no-print-directory", "up"], check=False)

    for failure in failures:
        print(f"unhealthy-check: FAIL {failure}", file=sys.stderr)
    if not failures:
        print("unhealthy-check: PASS (make status and the smoke test named the stopped db)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
