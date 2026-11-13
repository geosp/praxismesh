"""The PraxisMesh CLI (RFC Phase 1). Run through make, which loads infra/.env:

    uv run --env-file infra/.env python -m orchestrator.cli task submit \\
        --profile default --instructions "..." [--input FILE] [--output PATH] [--task-id ID]
    uv run --env-file infra/.env python -m orchestrator.cli task status TASK_ID
    uv run --env-file infra/.env python -m orchestrator.cli task output TASK_ID PATH [--to FILE]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from common.blob_store.s3 import S3BlobStore
from common.errors import InvalidTaskInput, PraxisError
from common.observability import (
    configure_logging,
    configure_tracing,
    log_context,
    tracing_interceptor,
)
from common.persistence.repositories import (
    AttemptRepository,
    CheckpointRepository,
    RecordingBlobStore,
    TaskRepository,
    make_engine,
)
from common.schemas import TaskResult
from orchestrator.submit import prepare_task, start_task
from registry.loader import load_registry

PROVIDER = configure_tracing("praxis-cli")
log = logging.getLogger("praxis.cli")


async def connect() -> Client:
    provider = PROVIDER
    return await Client.connect(
        f"127.0.0.1:{os.environ.get('TEMPORAL_PORT', '7233')}",
        namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"),
        data_converter=pydantic_data_converter,
        interceptors=[tracing_interceptor(provider)],
    )


async def submit(args: argparse.Namespace) -> int:
    if args.request:  # a raw JSON request, as a client would send it
        data: dict[str, Any] = json.loads(Path(args.request).read_text())
        return await _submit(data, args.wait)
    data = {"profile": args.profile, "instructions": args.instructions}
    if args.instructions_file:
        data["instructions"] = Path(args.instructions_file).read_text()
    if args.task_id:
        data["task_id"] = args.task_id
    if args.template:
        data["template"] = args.template
    data["input_files"] = args.input or []
    data["outputs"] = args.output or []
    return await _submit(data, args.wait)


async def _submit(data: dict[str, Any], wait: bool) -> int:
    engine = make_engine()
    try:
        s3 = S3BlobStore.from_env()
        await s3.ensure_bucket()
        start = await prepare_task(
            data, load_registry(), RecordingBlobStore(s3, engine), base_dir=Path.cwd()
        )
        tracer = PROVIDER.get_tracer("praxismesh.cli")
        with (
            log_context(task_id=start.task_id, request_id=start.request_id),
            tracer.start_as_current_span(
                "praxis.task.submit", attributes={"praxis.task_id": start.task_id}
            ),
        ):
            handle = await start_task(await connect(), start)
            log.info("task submitted", extra={"fields": {"template": start.template}})
    finally:
        await engine.dispose()
    print(json.dumps({"task_id": start.task_id, "request_id": start.request_id}), flush=True)
    if wait:
        result = TaskResult.model_validate(await handle.result())
        print(result.model_dump_json(indent=2))
        return 0 if result.status == "succeeded" else 1
    return 0


async def output(args: argparse.Namespace) -> int:
    engine = make_engine()
    try:
        row = await TaskRepository(engine).get(args.task_id)
    finally:
        await engine.dispose()
    if row is None or not row.get("result"):
        raise InvalidTaskInput(f"task {args.task_id} has no result yet")
    result = TaskResult.model_validate(row["result"])
    artifact = next((a for a in result.artifacts if a.path == args.path), None)
    if artifact is None:
        names = ", ".join(a.path for a in result.artifacts) or "none"
        raise InvalidTaskInput(
            f"task {args.task_id} has no output {args.path!r} (outputs: {names})"
        )
    data = await S3BlobStore.from_env().get(artifact.ref)
    if args.to:
        Path(args.to).write_bytes(data)
    else:
        sys.stdout.buffer.write(data)
    return 0


async def status(args: argparse.Namespace) -> int:
    """The task row, its attempts, its latest checkpoint and the Workflow status."""
    engine = make_engine()
    try:
        row = await TaskRepository(engine).get(args.task_id)
        attempts = await AttemptRepository(engine).list(args.task_id)
        latest = await CheckpointRepository(engine).latest(args.task_id)
        checkpoints = await CheckpointRepository(engine).count(args.task_id)
        orders = await TaskRepository(engine).sample_orders(args.task_id)
    finally:
        await engine.dispose()
    client = await connect()
    try:
        description = await client.get_workflow_handle(args.task_id).describe()
        workflow_status = description.status.name if description.status else "UNKNOWN"
    except Exception as e:  # the Workflow may be outside Temporal's retention
        workflow_status = f"unavailable ({type(e).__name__})"
    print(
        json.dumps(
            {
                "task_id": args.task_id,
                "workflow": workflow_status,
                "task": row,
                "attempts": attempts,
                "checkpoints": checkpoints,
                "latest_checkpoint": (
                    {
                        "checkpoint_id": latest.checkpoint_id,
                        "turn": latest.turn,
                        "attempt": latest.attempt,
                        "seq": latest.seq,
                        "session_position": latest.session_position,
                    }
                    if latest
                    else None
                ),
                "orders": orders,
            },
            default=str,
        )
    )
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="praxis")
    commands = p.add_subparsers(dest="group", required=True)
    task = commands.add_parser("task").add_subparsers(dest="command", required=True)
    s = task.add_parser("submit", help="submit a task")
    s.add_argument("--profile", default="default")
    s.add_argument("--template")
    s.add_argument("--instructions", default="")
    s.add_argument("--instructions-file")
    s.add_argument("--input", action="append", help="input file, repeatable")
    s.add_argument("--output", action="append", help="workspace path to return, repeatable")
    s.add_argument("--task-id")
    s.add_argument("--wait", action="store_true", help="wait for and print the TaskResult")
    s.add_argument("--request", help="submit this JSON request file instead of the flags")
    st = task.add_parser("status", help="show a task")
    st.add_argument("task_id")
    o = task.add_parser("output", help="download one of a task's output files")
    o.add_argument("task_id")
    o.add_argument("path")
    o.add_argument("--to", help="write to this file instead of stdout")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"), stream=sys.stderr)
    handler = {"submit": submit, "status": status, "output": output}[args.command]
    try:
        return asyncio.run(handler(args))
    except PraxisError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    finally:
        PROVIDER.shutdown()  # flush spans before exiting


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
