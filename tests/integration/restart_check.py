"""`make restart-check`: a repeat start changes nothing, and state survives a restart
(local-stack spec: Repeat start, Persistent state).

    up, migrate -> snapshot Temporal's schema versions and namespace -> up again
    -> snapshot unchanged -> seed (a Workflow and an object) -> down, up
    -> migrate (no change) -> Workflow still listed, object reads back the same
    -> clean up

Run through make, which loads infra/.env: make restart-check
"""

from __future__ import annotations

import asyncio
import contextlib
import subprocess
import sys

from botocore.exceptions import ClientError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest

from common.persistence.settings import app_database_url
from tests.support.stack import (
    env,
    run_hello,
    run_id,
    s3_client,
    temporal_client,
    wait_until_listed,
)

BODY = b"praxismesh restart check"
TEMPORAL_ROLE = {"user": "temporal", "password_var": "TEMPORAL_DB_PASSWORD"}


def make(target: str) -> None:
    print(f"restart-check: make {target}", flush=True)
    subprocess.run(["make", "--no-print-directory", target], check=True)


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


async def main() -> int:
    failures: list[str] = []
    make("up")
    make("migrate")

    before_repeat = await temporal_snapshot()
    make("up")
    after_repeat = await temporal_snapshot()
    failures += [
        f"repeat make up changed {key}"
        for key in before_repeat
        if before_repeat[key] != after_repeat[key]
    ]

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
        with contextlib.suppress(ClientError):
            s3.delete_object(Bucket=bucket, Key="seed.txt")
            s3.delete_bucket(Bucket=bucket)

    for failure in failures:
        print(f"restart-check: FAIL {failure}", file=sys.stderr)
    if not failures:
        print(
            f"restart-check: PASS (repeat start changed nothing; revision {before}; "
            "Workflow and object survived)"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
