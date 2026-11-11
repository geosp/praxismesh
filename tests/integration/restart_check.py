"""`make restart-check`: state survives a stack restart (local-stack spec, Persistent state).

    up, migrate -> seed (a Workflow and an object) -> down, up -> migrate (no change)
    -> the Workflow is still listed and the object reads back the same -> clean up

Run through make, which loads infra/.env: make restart-check
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from common.persistence.settings import app_database_url
from tests.support.stack import run_hello, run_id, s3_client, temporal_client, wait_until_listed

BODY = b"praxismesh restart check"


def make(target: str) -> None:
    print(f"restart-check: make {target}", flush=True)
    subprocess.run(["make", "--no-print-directory", target], check=True)


async def revision() -> str:
    engine = create_async_engine(app_database_url())
    try:
        async with engine.connect() as conn:
            return str(
                (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
            )
    finally:
        await engine.dispose()


async def main() -> int:
    make("up")
    make("migrate")
    before = await revision()

    rid = run_id()
    workflow_id, bucket = f"phase0-restart-{rid}", f"phase0-restart-{rid}"
    await run_hello(await temporal_client(), workflow_id, "restart")
    s3 = s3_client()
    s3.create_bucket(Bucket=bucket)
    s3.put_object(Bucket=bucket, Key="seed.txt", Body=BODY)
    print(f"restart-check: seeded Workflow {workflow_id} and s3://{bucket}/seed.txt", flush=True)

    make("down")
    make("up")
    make("migrate")

    failures = []
    if (after := await revision()) != before:
        failures.append(f"migration revision changed across restart: {before} -> {after}")
    client = await temporal_client()
    if not await wait_until_listed(client, workflow_id):
        failures.append(f"Workflow {workflow_id} is not listed after restart")
    elif (await client.get_workflow_handle(workflow_id).result()) != "Hello, restart!":
        failures.append(f"Workflow {workflow_id} result changed after restart")
    s3 = s3_client()
    if s3.get_object(Bucket=bucket, Key="seed.txt")["Body"].read() != BODY:
        failures.append(f"object s3://{bucket}/seed.txt changed after restart")

    s3.delete_object(Bucket=bucket, Key="seed.txt")
    s3.delete_bucket(Bucket=bucket)

    for failure in failures:
        print(f"restart-check: FAIL {failure}", file=sys.stderr)
    if not failures:
        print(f"restart-check: PASS (revision {before}, Workflow and object survived)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
