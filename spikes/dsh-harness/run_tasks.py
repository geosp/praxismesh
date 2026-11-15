"""R7 native fixtures through the existing TaskWorkflow and real local services.

Run from the repository root with uv run --env-file infra/.env. The candidate
receives none of that host environment: Docker grants stay explicitly enumerated.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from run_probe import HERE, IMAGE, ROOT, image_id

sys.path.insert(0, str(ROOT))

from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import text
from task_activity import TaskActivities
from temporalio.worker import Worker

from common.blob_store.s3 import S3BlobStore
from common.persistence.repositories import RecordingBlobStore, TaskRepository, make_engine
from common.schemas import TaskResult
from orchestrator.activities import OrchestratorActivities
from orchestrator.constants import orchestration_queue, template_queue
from orchestrator.submit import prepare_task, start_task
from orchestrator.workflow import TaskWorkflow
from registry.loader import load_registry
from workers.main import connect

CASES = (
    "done",
    "plain-text",
    "inner-limit",
    "needs-input",
    "invalid-status",
    "invalid-payload",
    "invalid-reference",
    "retry-model",
    "retry-protocol",
    "retry-infrastructure",
    "bad-request",
)


async def run_case(case: str, image: str, scratch: Path) -> dict:
    engine = make_engine()
    registry = load_registry()
    s3 = S3BlobStore.from_env()
    records = {"case": case, "exit": 1, "status": "blocked"}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        await s3.ensure_bucket()
        client = await connect("dsh-spike", TracerProvider())
        prefix = "dsh-spike-" + uuid.uuid4().hex[:12] + "."
        os.environ["PRAXIS_QUEUE_PREFIX"] = prefix
        blobs = RecordingBlobStore(s3, engine)
        coordinator = OrchestratorActivities(registry, TaskRepository(engine))
        candidate = TaskActivities(engine, blobs, scratch / "activities", image, case)
        inputs = scratch / "inputs"
        inputs.mkdir(parents=True)
        (inputs / "answer.txt").write_text("controlled fixture artifact\n")
        start = await prepare_task(
            {
                "profile": "default",
                "instructions": "Execute the controlled completion fixture.",
                "input_files": ["answer.txt"],
                "outputs": ["answer.txt"],
            },
            registry,
            blobs,
            base_dir=inputs,
        )
        records.update(task_id=start.task_id, queue_prefix=prefix, status="running")
        orchestrator = Worker(
            client,
            task_queue=orchestration_queue(),
            workflows=[TaskWorkflow],
            activities=[
                coordinator.resolve_capabilities,
                coordinator.record_task,
                coordinator.complete_task,
            ],
        )
        worker = Worker(
            client,
            task_queue=template_queue("local-default"),
            activities=[candidate.run_harness_turn],
            max_concurrent_activities=1,
        )
        async with orchestrator, worker:
            handle = await start_task(client, start)
            result = TaskResult.model_validate(await asyncio.wait_for(handle.result(), timeout=900))
        records.update(result=result.model_dump(mode="json"), native_attempts=candidate.records)
        expected = (
            "failed"
            if case in ("plain-text", "inner-limit", "bad-request")
            else "needs_input"
            if case == "needs-input"
            else "succeeded"
        )
        if result.status != expected:
            raise AssertionError("unexpected TaskResult status")
        if case == "needs-input" and result.questions != ["Which fixture value should be used?"]:
            raise AssertionError("questions were lost")
        if case.startswith("retry-") and result.attempts != 2:
            raise AssertionError("transient fixture did not retry exactly once through Temporal")
        if case == "bad-request" and result.attempts != 1:
            raise AssertionError("invalid model input was retried")
        if case in ("plain-text", "inner-limit") and result.turns != 6:
            raise AssertionError("continuation did not use the selected outer-turn budget")
        if result.status == "succeeded":
            if len(result.artifacts) != 1:
                raise AssertionError("expected trusted artifact reference")
            if await blobs.get(result.artifacts[0].ref) != b"controlled fixture artifact\n":
                raise AssertionError("artifact reference read-back failed")
        records.update(exit=0, status="passed")
    except Exception as error:
        records["error_type"] = type(error).__name__
        if isinstance(error, AssertionError):
            records.update(status="failed", error=str(error))
        elif records["status"] == "running":
            records["status"] = "failed"
    finally:
        await engine.dispose()
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=(*CASES, "all"))
    parser.add_argument("--image", type=image_id, default=IMAGE)
    args = parser.parse_args()
    name = "task-workflow-" + uuid.uuid4().hex[:12]
    scratch = HERE / ".runs" / name
    scratch.mkdir(parents=True)
    results = []
    for case in CASES if args.case == "all" else (args.case,):
        result = asyncio.run(run_case(case, args.image, scratch / case))
        results.append(result)
        (scratch / (case + "-result.json")).write_text(json.dumps(result, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "case": case,
                    "status": result["status"],
                    "exit": result["exit"],
                    "error_type": result.get("error_type"),
                }
            ),
            flush=True,
        )
        if result["status"] == "blocked":
            break
    return int(any(r["exit"] for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
