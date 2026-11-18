"""Event-table load benchmark (Phase 2 events plan task 2.3; Risks).

    uv run --env-file infra/.env python -m tests.benchmarks.event_load \\
        [--seconds 180] [--agents 4] [--tailers 3] [--runs 3] [--label NAME]

The event-transport spike's synthetic load (spike `load.py`, issue #76), on the
production path: each agent is a recorded task with a started attempt whose events
go through `AttemptEvents` and a `BatchingPublisher` to the table, at ~50 `token`
events/s plus a `tool_call`/`tool_result` pair every 10 s. Each agent has
`--tailers` following readers from offset 0; one per agent is stopped and resumed
from its last offset every 60 s. The runs alternate fenced and one unfenced
baseline in one session, so database CPU compares like with like.

Passes when, in every fenced run, publish-to-display p95 is at most 1 s (the
spike's R6) and publish p95 under 250 ms, every tailer saw every offset once, and
the median fenced database CPU is at most double the unfenced run's. Results go to
docs/benchmarks/<date>-event-load.json with the commit and command.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import statistics
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from common.events import EventTransport, Expired, TableTransport, Writer
from common.persistence.repositories import AttemptRepository, TaskRepository, make_engine
from common.schemas import BlobRef, TaskStart
from common.schemas.events import AgentEvent
from harness_activity.events import AttemptEvents, BatchingPublisher

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "docs" / "benchmarks"
RATE_PER_S = 50
TOOL_EVERY_S = 10.0
RESTART_EVERY_S = 60.0
DISPLAY_P95_S, PUBLISH_P95_S, CPU_RATIO = 1.0, 0.25, 2.0


class Timed(TableTransport):
    """The table transport, timing each publish."""

    def __init__(self, engine: AsyncEngine, *, fenced: bool) -> None:
        super().__init__(engine, fenced=fenced)
        self.publish_s: list[float] = []

    async def publish(
        self, workflow_id: str, writer: Writer, batch_id: str, events: list[AgentEvent]
    ) -> None:
        started = time.monotonic()
        await super().publish(workflow_id, writer, batch_id, events)
        self.publish_s.append(time.monotonic() - started)


@dataclass
class Tailer:
    seen: list[int] = field(default_factory=list)
    latency_s: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


async def tail(
    t: EventTransport, wf: str, tailer: Tailer, stop: asyncio.Event, restart: bool
) -> None:
    """Follow from 0; with `restart`, stop and resume from the last offset every 60 s.
    Each reader runs in its own task, cancelled only to stop it: cancelling a pending
    `anext` would close the generator (the spike's impl review)."""

    async def consume(after: int) -> None:
        async for item in t.read(wf, after, follow=True):
            if isinstance(item, Expired):
                tailer.errors.append(f"unexpected expiry at {item.retained_base}")
                continue
            offset, event = item
            if tailer.seen and offset != tailer.seen[-1] + 1:
                tailer.errors.append(f"offset {offset} after {tailer.seen[-1]}")
            tailer.seen.append(offset)
            tailer.latency_s.append((datetime.now(UTC) - event.timestamp).total_seconds())

    stopped = asyncio.create_task(stop.wait())
    try:
        while not stop.is_set():
            reader = asyncio.create_task(consume(tailer.seen[-1] if tailer.seen else 0))
            await asyncio.wait(
                [reader, stopped],
                timeout=RESTART_EVERY_S if restart else None,
                return_when=asyncio.FIRST_COMPLETED,
            )
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader
    finally:
        stopped.cancel()


async def agent(engine: AsyncEngine) -> str:
    """One recorded task with a started attempt, publishing for `seconds`."""
    task_id = f"task-load-{uuid.uuid4().hex[:12]}"
    ref = BlobRef(
        id=f"blob:{0:064x}",
        key=f"sha256/{0:064x}",
        checksum=f"sha256:{0:064x}",
        content_type="text/plain",
        bytes=1,
        retention_class="task",
        created_at=datetime.now(UTC),
    )
    start = TaskStart(
        task_id=task_id, request_id="req-load", profile="dsh", template="local-dsh",
        instructions_ref=ref,
    )  # fmt: skip
    await TaskRepository(engine).record_task(
        start, workflow_id=task_id, run_id="load", template_version=1, template_hash="load"
    )
    await AttemptRepository(engine).start(task_id, 1, 1, "load")
    return task_id


async def publish_for(t: EventTransport, task_id: str, seconds: float) -> int:
    publisher = BatchingPublisher(t, Writer(task_id, 1, 1), task_id, f"{task_id}:1:1")
    events = AttemptEvents(publisher, task_id, task_id, 1, 1)
    end, next_tool, n = time.monotonic() + seconds, time.monotonic() + TOOL_EVERY_S, 0
    while time.monotonic() < end:
        events.emit("token", input_tokens=n, output_tokens=1)
        n += 1
        if time.monotonic() >= next_tool:
            events.emit("tool_call", tool="lookup_price", call=n)
            events.emit("tool_result", tool="lookup_price", call=n, status="ok")
            n, next_tool = n + 2, next_tool + TOOL_EVERY_S
        await asyncio.sleep(1 / RATE_PER_S)
    problem = await publisher.close()
    if problem is not None:
        raise RuntimeError(f"publisher: {problem!r}")
    return n


def p95(values: list[float]) -> float | None:
    return statistics.quantiles(values, n=100)[94] if len(values) >= 2 else None


def sampler(names: list[str], samples: list[dict[str, Any]], stop: threading.Event) -> None:
    while not stop.is_set():
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}", *names],
            capture_output=True, text=True, check=False,
        ).stdout  # fmt: skip
        for line in out.splitlines():
            name, _, cpu = line.partition("|")
            if cpu:
                samples.append({"name": name, "cpu": float(cpu.rstrip("%") or 0)})
        stop.wait(5)


async def one_run(args: argparse.Namespace, fenced: bool) -> dict[str, Any]:
    engine = make_engine()
    t = Timed(engine, fenced=fenced)
    project = os.environ.get("COMPOSE_PROJECT_NAME", "praxismesh")
    samples: list[dict[str, Any]] = []
    stop_sampling = threading.Event()
    threading.Thread(
        target=sampler, args=([f"{project}-db-1"], samples, stop_sampling), daemon=True
    ).start()
    try:
        tasks = [await agent(engine) for _ in range(args.agents)]
        stop = asyncio.Event()
        tailers = {wf: [Tailer() for _ in range(args.tailers)] for wf in tasks}
        readers = [
            asyncio.create_task(tail(t, wf, tl, stop, restart=i == 0))
            for wf in tasks
            for i, tl in enumerate(tailers[wf])
        ]
        published = await asyncio.gather(*(publish_for(t, wf, args.seconds) for wf in tasks))
        await asyncio.sleep(3)  # let tailers catch up
        stop.set()
        await asyncio.gather(*readers)
        latencies = [x for wf in tasks for tl in tailers[wf] for x in tl.latency_s]
        complete = all(
            tl.seen == list(range(1, n + 1)) and not tl.errors
            for wf, n in zip(tasks, published, strict=True)
            for tl in tailers[wf]
        )
    finally:
        stop_sampling.set()
        await engine.dispose()
    cpu = [s["cpu"] for s in samples]
    return {
        "fenced": fenced,
        "events_published": sum(published),
        "publishes": len(t.publish_s),
        "publish_p95_s": p95(t.publish_s),
        "display_p95_s": p95(latencies),
        "display_median_s": statistics.median(latencies) if latencies else None,
        "tailers_complete": complete,
        "db_cpu_median_pct": statistics.median(cpu) if cpu else None,
        "db_cpu_samples": len(cpu),
    }


def judge(runs: list[dict[str, Any]]) -> dict[str, bool]:
    fenced = [r for r in runs if r["fenced"]]
    unfenced = [r for r in runs if not r["fenced"]]
    fenced_cpu = statistics.median(r["db_cpu_median_pct"] or 0 for r in fenced)
    base_cpu = statistics.median(r["db_cpu_median_pct"] or 0 for r in unfenced)
    return {
        "display_p95": all((r["display_p95_s"] or 99) <= DISPLAY_P95_S for r in fenced),
        "publish_p95": all((r["publish_p95_s"] or 99) < PUBLISH_P95_S for r in fenced),
        "tailers_complete": all(r["tailers_complete"] for r in runs),
        "db_cpu_ratio": base_cpu > 0 and fenced_cpu <= CPU_RATIO * base_cpu,
    }


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT).stdout.strip()


async def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="event_load")
    p.add_argument("--seconds", type=float, default=180)
    p.add_argument("--agents", type=int, default=4)
    p.add_argument("--tailers", type=int, default=3)
    p.add_argument("--runs", type=int, default=3, help="fenced runs; one unfenced run follows")
    p.add_argument("--label", default="")
    p.add_argument("--out", type=Path, help="write here instead of docs/benchmarks/")
    args = p.parse_args(argv)
    runs: list[dict[str, Any]] = []
    for fenced in [True] * args.runs + [False]:
        print(f"run {len(runs) + 1}: fenced={fenced}", file=sys.stderr, flush=True)
        runs.append(await one_run(args, fenced))
        print(json.dumps(runs[-1]), file=sys.stderr, flush=True)
    verdict = judge(runs)
    result = {
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain", "--", "common", "harness_activity", "tests")),
        "command": "python -m tests.benchmarks.event_load " + " ".join(argv),
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "settings": vars(args) | {"out": str(args.out) if args.out else None},
        "thresholds": {
            "display_p95_s": DISPLAY_P95_S,
            "publish_p95_s": PUBLISH_P95_S,
            "db_cpu_ratio": CPU_RATIO,
        },
        "runs": runs,
        "verdict": verdict,
        "pass": all(verdict.values()),
    }
    label = f"-{args.label}" if args.label else ""
    out = args.out or RESULTS / f"{datetime.now(UTC):%Y-%m-%d}-event-load{label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"out": str(out), "verdict": verdict, "pass": result["pass"]}))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        sys.exit(asyncio.run(main(sys.argv[1:])))
