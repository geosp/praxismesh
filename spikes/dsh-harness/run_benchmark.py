"""R8: the ten existing benchmark tasks through TaskWorkflow and the isolated DSH Activity.

Run from the repository root with uv run --env-file infra/.env and the
benchmark image (Dockerfile.benchmark). Results stay under .runs/; the recorded
baseline in docs/benchmarks/ is read, never written.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path

from run_probe import HERE, ROOT, host_memory_available, image_id

sys.path.insert(0, str(ROOT))

from opentelemetry.sdk.trace import TracerProvider
from recovery_store import Authority, restore_pair
from task_activity import CLI_GRANT, PRODUCTION_PROMPT, SHOP_GRANT, TaskActivities
from temporalio.worker import Worker

from common.blob_store.s3 import S3BlobStore
from common.persistence.repositories import RecordingBlobStore, TaskRepository, make_engine
from common.schemas import TaskResult
from orchestrator.activities import OrchestratorActivities
from orchestrator.constants import orchestration_queue, template_queue
from orchestrator.submit import prepare_task, start_task
from orchestrator.workflow import TaskWorkflow
from registry.loader import load_registry
from tests.benchmarks.agent_tasks.tasks import TASKS, setup
from tests.benchmarks.run import BASELINE, REGRESSION_LIMIT
from workers.main import connect

MEMORY_FLOOR = 4 << 30


async def run_all(ids: list[str], image: str, scratch: Path) -> list[dict]:
    engine = make_engine()
    registry = load_registry()
    s3 = S3BlobStore.from_env()
    await s3.ensure_bucket()
    blobs = RecordingBlobStore(s3, engine)
    client = await connect("dsh-spike", TracerProvider())
    os.environ["PRAXIS_QUEUE_PREFIX"] = "dsh-spike-" + uuid.uuid4().hex[:12] + "."
    coordinator = OrchestratorActivities(registry, TaskRepository(engine))
    candidate = TaskActivities(engine, blobs, scratch / "activities", image, "benchmark")
    rows = []
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
    try:
        async with orchestrator, worker:
            for task in [t for t in TASKS if not ids or t.id in ids]:
                available = host_memory_available()
                if available < MEMORY_FLOOR:
                    # Stop before starting a candidate; an unfinished run is not evidence.
                    rows.append(
                        {
                            "task": task.id,
                            "passed": False,
                            "status": "blocked",
                            "check": f"blocked: host memory {available >> 20} MiB available",
                        }
                    )
                    print(json.dumps(rows[-1]), flush=True)
                    break
                inputs = scratch / "inputs" / task.id
                setup(task, inputs)
                start = await prepare_task(
                    {
                        "profile": "default",
                        "instructions": task.prompt,
                        "input_files": [str(p) for p in sorted(inputs.iterdir())],
                    },
                    registry,
                    blobs,
                    base_dir=inputs,
                )
                before = len(candidate.records)
                began = time.monotonic()
                result: TaskResult | None = None
                try:
                    handle = await start_task(client, start)
                    result = TaskResult.model_validate(
                        await asyncio.wait_for(handle.result(), timeout=1800)
                    )
                    status, reason = result.status, result.failure_reason
                except Exception as error:
                    status, reason = "error", type(error).__name__
                seconds = round(time.monotonic() - began, 1)
                attempts = candidate.records[before:]
                authority = scratch / "activities" / start.task_id / "authority.sqlite"
                final = scratch / "final" / task.id
                if authority.exists() and Authority(authority).publication() is not None:
                    final.parent.mkdir(parents=True, exist_ok=True)
                    restore_pair(Authority(authority).restore()[1], final)
                    passed, check = task.check(final / "workspace")
                else:
                    passed, check = False, "no acknowledged checkpoint"
                totals = [a.get("totals") or {} for a in attempts]
                row = {
                    "task": task.id,
                    "task_id": start.task_id,
                    "passed": passed,
                    "check": check,
                    "status": status,
                    "failure_reason": reason,
                    "turns": result.turns if result else None,
                    "attempts": result.attempts if result else None,
                    "inner_turns": result.inner_turns if result else None,
                    "tokens_in": result.tokens_in if result else None,
                    "tokens_out": result.tokens_out if result else None,
                    "model_dispatches": sum(t.get("physical_dispatches") or 0 for t in totals),
                    "tool_entries": sum(
                        sum(e["admitted"] for e in a.get("tool_entries") or []) for a in attempts
                    ),
                    "native_attempts": len(attempts),
                    "native_failures": [a.get("error_type") for a in attempts if a.get("exit")],
                    "cleanup_ok": all(a.get("cleanup", {}).get("cleanup_ok") for a in attempts),
                    "seconds": seconds,
                }
                rows.append(row)
                print(json.dumps({k: row[k] for k in ("task", "passed", "check", "status")}))
    finally:
        await engine.dispose()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=image_id, required=True)
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()
    name = "benchmark-" + uuid.uuid4().hex[:12]
    scratch = HERE / ".runs" / name
    scratch.mkdir(parents=True)
    rows = asyncio.run(run_all(args.only, args.image, scratch))
    baseline = json.loads(BASELINE.read_text())
    passed = sum(r["passed"] for r in rows)
    complete = sum(r["status"] != "blocked" for r in rows) == len(TASKS)
    lost = baseline["passed"] - passed
    summary = {
        "image": args.image,
        "baseline": {k: baseline[k] for k in ("passed", "template_hash", "prompt_hash", "harness")},
        "candidate_prompt_sha256": "sha256:"
        + hashlib.sha256(PRODUCTION_PROMPT.encode()).hexdigest(),
        "cli_tools": CLI_GRANT,
        "shop_tools": list(SHOP_GRANT),
        "passed": passed,
        "ran": len(rows),
        "complete": complete,
        "lost": lost,
        "regression_limit_exceeded": lost >= REGRESSION_LIMIT,
        "rows": rows,
    }
    (scratch / "benchmark.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in ("passed", "ran", "complete", "lost")}))
    return 0 if complete and not summary["regression_limit_exceeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
