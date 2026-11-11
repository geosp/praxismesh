"""`make restart-check`: a repeat start changes nothing, a changed retention is
applied, and state survives a restart (local-stack spec: Repeat start, Changed
retention, Persistent state).

    up, migrate -> snapshot Temporal's schema versions and namespace
    -> up again (running stack) -> unchanged
    -> stop, up (stopped stack) -> unchanged
    -> up with another retention -> applied -> up as configured -> restored
    -> seed (a Workflow and an object) -> down, up -> migrate (no change)
    -> Workflow still listed, object reads back the same -> clean up

Run through make, which loads infra/.env: make restart-check
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import sys

from botocore.exceptions import ClientError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest

from common.persistence.settings import app_database_url
from tests.support.stack import (
    env,
    retention_seconds,
    run_hello,
    run_id,
    s3_client,
    temporal_client,
    wait_until_listed,
)

BODY = b"praxismesh restart check"
TEMPORAL_ROLE = {"user": "temporal", "password_var": "TEMPORAL_DB_PASSWORD"}


OTHER_RETENTION = "96h"
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    os.environ.get("ENV_FILE", "infra/.env"),
    "-f",
    "infra/docker-compose.yml",
]


def make(target: str, **env_overrides: str) -> None:
    shown = " ".join(f"{k}={v}" for k, v in env_overrides.items())
    print(f"restart-check: {shown + ' ' if shown else ''}make {target}", flush=True)
    subprocess.run(
        ["make", "--no-print-directory", target], check=True, env={**os.environ, **env_overrides}
    )


def namespace_job_log() -> str:
    return subprocess.run(
        [*COMPOSE, "logs", "--no-log-prefix", "temporal-namespace"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


async def retention_now() -> int:
    client = await temporal_client()
    described = await client.workflow_service.describe_namespace(
        DescribeNamespaceRequest(namespace=env("TEMPORAL_NAMESPACE", "default"))
    )
    return int(described.config.workflow_execution_retention_ttl.ToSeconds())


async def query(sql: str, **url_args: str) -> list[tuple[object, ...]]:
    engine = create_async_engine(app_database_url(**url_args))
    try:
        async with engine.connect() as conn:
            return [tuple(row) for row in (await conn.execute(text(sql))).all()]
    finally:
        await engine.dispose()


async def revision() -> str:
    return str((await query("SELECT version_num FROM alembic_version"))[0][0])


async def temporal_snapshot() -> dict[str, object]:
    """Schema version rows and update history in both Temporal databases, plus the
    namespace description. A repeat start must leave all of it unchanged."""
    snapshot: dict[str, object] = {}
    for database in ("temporal", "temporal_visibility"):
        snapshot[f"{database}.schema_version"] = await query(
            "SELECT * FROM schema_version ORDER BY 1", database=database, **TEMPORAL_ROLE
        )
        snapshot[f"{database}.schema_update_history"] = await query(
            "SELECT * FROM schema_update_history ORDER BY 1, 2, 3, 4",
            database=database,
            **TEMPORAL_ROLE,
        )
    client = await temporal_client()
    described = await client.workflow_service.describe_namespace(
        DescribeNamespaceRequest(namespace=env("TEMPORAL_NAMESPACE", "default"))
    )
    snapshot["namespace.config"] = described.config.SerializeToString(deterministic=True)
    snapshot["namespace.info"] = described.namespace_info.SerializeToString(deterministic=True)
    return snapshot


def compare(label: str, before: dict[str, object], after: dict[str, object]) -> list[str]:
    return [f"{label} changed {key}" for key in before if before[key] != after[key]]


async def main() -> int:
    failures: list[str] = []
    make("up")
    make("migrate")

    baseline = await temporal_snapshot()
    make("up")
    failures += compare("repeat make up on a running stack", baseline, await temporal_snapshot())
    # The API exposes no config version, so the job's own log shows that it ran
    # and issued no update (an update would log "updating" instead).
    if "exists with retention" not in namespace_job_log():
        failures.append("the namespace job did not run, or updated the namespace, on repeat")

    print("restart-check: stopping the stack (containers kept)", flush=True)
    subprocess.run([*COMPOSE, "stop"], check=True, capture_output=True)
    make("up")
    failures += compare("repeat make up on a stopped stack", baseline, await temporal_snapshot())

    configured = retention_seconds(env("TEMPORAL_RETENTION"))
    make("up", TEMPORAL_RETENTION=OTHER_RETENTION)
    if (got := await retention_now()) != retention_seconds(OTHER_RETENTION):
        failures.append(f"retention {OTHER_RETENTION} was not applied (namespace has {got}s)")
    make("up")
    if (got := await retention_now()) != configured:
        failures.append(f"configured retention was not restored (namespace has {got}s)")

    before = await revision()
    rid = run_id()
    workflow_id, bucket = f"phase0-restart-{rid}", f"phase0-restart-{rid}"
    s3 = s3_client()
    try:
        await run_hello(await temporal_client(), workflow_id, "restart")
        s3.create_bucket(Bucket=bucket)
        s3.put_object(Bucket=bucket, Key="seed.txt", Body=BODY)
        print(
            f"restart-check: seeded Workflow {workflow_id} and s3://{bucket}/seed.txt", flush=True
        )

        make("down")
        make("up")
        make("migrate")

        if (after := await revision()) != before:
            failures.append(f"migration revision changed across restart: {before} -> {after}")
        client = await temporal_client()
        if not await wait_until_listed(client, workflow_id):
            failures.append(f"Workflow {workflow_id} is not listed after restart")
        elif (await client.get_workflow_handle(workflow_id).result()) != "Hello, restart!":
            failures.append(f"Workflow {workflow_id} result changed after restart")
        s3 = s3_client()
        try:
            if s3.get_object(Bucket=bucket, Key="seed.txt")["Body"].read() != BODY:
                failures.append(f"object s3://{bucket}/seed.txt changed after restart")
        except ClientError as e:
            failures.append(f"object s3://{bucket}/seed.txt is gone after restart: {e}")
    finally:
        # Best effort: never replace the real error (the stack may be down).
        with contextlib.suppress(Exception):
            s3.delete_object(Bucket=bucket, Key="seed.txt")
            s3.delete_bucket(Bucket=bucket)

    for failure in failures:
        print(f"restart-check: FAIL {failure}", file=sys.stderr)
    if not failures:
        print(
            f"restart-check: PASS (repeat starts changed nothing; retention change applied "
            f"and restored; revision {before}; Workflow and object survived)"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
