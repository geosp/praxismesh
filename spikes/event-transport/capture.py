"""Capture the recorded DSH turn (event-transport spike task 1.3, plan D3, R7).

Run once, from the repository root, in the root environment:

    PYTHONPATH=. uv run --env-file infra/.env python spikes/event-transport/capture.py

It starts its own DSH container, drives one turn of the benchmark task
`t01-order-total` through `DshRunner.run` against the real model (VLLM_BASE_URL),
with a recording sink, and writes the events as JSON lines to
`spikes/event-transport/fixtures/dsh-turn-t01.jsonl`. No database is used and no
production code changes. Payloads hold request IDs, token counts, tool names,
call numbers and outcomes only.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# The spike's own `tests` package sits beside this script and would shadow the
# repository's: put the repository root first instead.
sys.path[0] = str(Path(__file__).resolve().parents[2])

from harness_activity.config import build_config  # noqa: E402
from harness_activity.events import MemorySink  # noqa: E402
from harness_activity.runner import AttemptContext, Usage  # noqa: E402
from registry.loader import load_registry  # noqa: E402
from tests.benchmarks.agent_tasks.tasks import TASKS, setup  # noqa: E402
from tests.support.dsh_container import build_image, start_container  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures" / "dsh-turn-t01.jsonl"
TASK = "t01-order-total"
MIN_EVENTS = 10


async def _no_op(usage: Usage) -> None:
    return None


async def capture() -> int:
    if not os.environ.get("VLLM_BASE_URL"):
        print("error: VLLM_BASE_URL is not set; run with --env-file infra/.env", file=sys.stderr)
        return 2
    task = next(t for t in TASKS if t.id == TASK)
    sink = MemorySink()
    container = start_container(build_image())
    try:
        registry = load_registry()
        task_id = "task-spike76-capture"
        config = build_config(registry, registry.templates["local-dsh"], task_id)
        runner = container.runner(sink)
        scope = await runner.open_attempt(
            AttemptContext(task_id, 1, 1, task_id, 1_000_000, time.monotonic() + 600)
        )
        try:
            setup(task, scope.workspace)
            result = await runner.run(
                config, scope.workspace, scope.store.session, task.prompt, _no_op, Usage()
            )
        finally:
            await scope.close()
    finally:
        container.stop()
    if len(sink.events) < MIN_EVENTS:  # keep the committed fixture (impl review F42)
        print(f"error: only {len(sink.events)} events; fixture left unchanged", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text("".join(e.model_dump_json() + "\n" for e in sink.events))
    tmp.replace(OUT)
    print(f"turn ended: {result.status}; {len(sink.events)} events -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(capture()))
