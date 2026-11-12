"""`make unhealthy-check`: a stopped database is reported by name (local-stack spec,
Unhealthy service).

    stop db -> `make status` fails naming db
    -> `make smoke` fails naming the database server -> start db, make up (must pass)

Run through make, which loads infra/.env: make unhealthy-check
"""

from __future__ import annotations

import os
import subprocess
import sys

COMPOSE = [
    "docker",
    "compose",
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
        last = (status.stdout.strip().splitlines() or ["(no output)"])[-1]
        print(f"unhealthy-check: make status said: {last}")
        if status.returncode == 0 or "unhealthy or stopped: db" not in status.stdout:
            failures.append(f"make status did not name db (exit {status.returncode})")

        smoke = run(["make", "--no-print-directory", "smoke"])
        named = [
            line
            for line in smoke.stdout.splitlines()
            if "RuntimeError: database server (service db)" in line
        ]
        if named:
            print(f"unhealthy-check: make smoke said: {named[0].strip()}")
        if smoke.returncode == 0:
            failures.append("the database smoke test passed with db stopped")
        elif not named:
            failures.append("the database smoke test failed without naming the database")
    finally:
        print("unhealthy-check: starting db and the stack", flush=True)
        if run([*COMPOSE, "start", "db"]).returncode != 0:
            failures.append("could not start db again")
        if subprocess.run(["make", "--no-print-directory", "up"], check=False).returncode != 0:
            failures.append("make up failed after restarting db; the stack is not healthy")

    for failure in failures:
        print(f"unhealthy-check: FAIL {failure}", file=sys.stderr)
    if not failures:
        print("unhealthy-check: PASS (make status and the smoke test named the stopped db)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
