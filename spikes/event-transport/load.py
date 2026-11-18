"""The load runner (plan R5, R6, R11; notes.md#d3, #d5; phase 02 task 1.1).

    uv run python load.py <option> [--seconds 300] [--agents 4] [--tailers 3]
                         [--label run1]

Each agent publishes from inside one long-running Activity (notes.md#d5, F32), the
same for every option: ~50 `token` events/s with a ~40-byte text delta, plus a
`tool_call`/`tool_result` pair every 10 s, batched every 200 ms or 64 events. Each
agent has `--tailers` following readers from offset 0; one per agent is stopped and
resumed from its last offset every 60 s. Results go to
`results/load-<option>-<label>.json`, with the commit and command.

Measured: publish-to-display latency of every event a tailer shows; per Streams
hosting run (none remain since ADR-0009; that code is at 1bfac67), history and carried
state; CPU and memory of the stack's database and Temporal containers.
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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from event_transport.factories import OPTIONS
from event_transport.models import AgentEvent
from event_transport.transport import EventTransport, Expired
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import Worker

SPIKE = Path(__file__).resolve().parent
RESULTS = SPIKE / "results"
ADDRESS = os.environ.get("SPIKE_TEMPORAL", "127.0.0.1:37233")
LOAD_QUEUE = "spike76-load"
RATE_PER_S = 50
BATCH_S, BATCH_MAX = 0.2, 64
TOOL_EVERY_S = 10.0
KILL_EVERY_S = 60.0
DELTA = "x" * 40  # stands in for ~40 bytes of token text (size only)
LIMIT_EVENTS, LIMIT_BYTES = 51_200, 50 * 1024 * 1024  # Temporal per-run history (task 1.1)
LIMIT_PAYLOAD = 2 * 1024 * 1024  # Temporal per-payload size


# ---- publishing agents: one long-running Activity each, the same for every option


@dataclass
class AgentInput:
    workflow_id: str
    seconds: float


@dataclass
class AgentResult:
    published: int = 0
    batches: int = 0
    publish_ms: list[float] = field(default_factory=list)


@workflow.defn(name="SpikeLoadAgent", sandboxed=False)
class LoadAgentWorkflow:
    @workflow.run
    async def run(self, inp: AgentInput) -> AgentResult:
        return await workflow.execute_activity(
            "spike_publish",
            inp,
            result_type=AgentResult,
            start_to_close_timeout=timedelta(seconds=inp.seconds + 120),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=1),  # a failed agent fails the run (F64)
        )


class Agents:
    def __init__(self, transport: EventTransport) -> None:
        self.transport = transport

    @activity.defn(name="spike_publish")
    async def publish(self, inp: AgentInput) -> AgentResult:
        """Open-loop (F61): a producer makes events on a fixed schedule and stamps each
        with the time it was due, so a slow publish shows as latency instead of
        lowering the load. Batch IDs name the attempt (F76)."""
        out, wf = AgentResult(), inp.workflow_id
        attempt = activity.info().attempt
        pending: list[AgentEvent] = []

        async def produce() -> None:
            start, start_wall, i, seq = time.monotonic(), time.time(), 0, 0
            next_tool = TOOL_EVERY_S
            while (due := i / RATE_PER_S) < inp.seconds:
                delay = start + due - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                kinds = ["token"]
                if due >= next_tool:
                    kinds += ["tool_call", "tool_result"]
                    next_tool += TOOL_EVERY_S
                for kind in kinds:
                    payload: dict[str, Any] = {"t": start_wall + due}
                    payload |= (
                        {"delta": DELTA}
                        if kind == "token"
                        else {"tool": "run_command", "call": seq}
                    )
                    pending.append(
                        AgentEvent(
                            seq=seq,
                            timestamp=datetime.now(UTC),
                            workflow_id=wf,
                            task_id=wf,
                            attempt_id=f"{wf}:1:{attempt}",
                            type=kind,  # type: ignore[arg-type]
                            payload=payload,
                        )
                    )
                    seq += 1
                i += 1

        producer = asyncio.create_task(produce())
        last = time.monotonic()
        try:
            while not (producer.done() and not pending):
                due = len(pending) >= BATCH_MAX or time.monotonic() - last >= BATCH_S
                if pending and (due or producer.done()):
                    batch = pending[:BATCH_MAX]
                    del pending[: len(batch)]
                    started = time.monotonic()
                    await self.transport.publish(wf, f"{wf}:{attempt}:{out.batches}", batch)
                    out.publish_ms.append((time.monotonic() - started) * 1000)
                    out.published += len(batch)
                    out.batches += 1
                    last = time.monotonic()
                    activity.heartbeat(out.published)
                else:
                    await asyncio.sleep(0.01)
            await producer  # re-raise anything the producer hit
        finally:
            producer.cancel()
        return out


# ---- tailers


@dataclass
class Tailer:
    workflow_id: str
    killable: bool
    last: int = 0
    shown: int = 0
    expired: list[int] = field(default_factory=list)
    latency_ms: list[float] = field(default_factory=list)
    restarts: int = 0
    error: str | None = None


async def tail(t: EventTransport, tailer: Tailer, stop: asyncio.Event) -> None:
    """Follow one workflow; a killable tailer is stopped and resumed from its last
    offset every KILL_EVERY_S. The reader runs in its own task and is cancelled only
    to stop it: cancelling a pending `anext` would end the reader for good."""

    async def consume() -> None:
        async for item in t.read(tailer.workflow_id, tailer.last, follow=True):
            if isinstance(item, Expired):
                tailer.expired.append(item.retained_base)
                continue
            offset, event = item
            tailer.latency_ms.append((time.time() - event.payload["t"]) * 1000)
            tailer.last, tailer.shown = offset, tailer.shown + 1

    while not stop.is_set():
        reader = asyncio.create_task(consume())
        stopper = asyncio.create_task(stop.wait())
        timeout = KILL_EVERY_S if tailer.killable else None
        done, _ = await asyncio.wait(
            {reader, stopper}, timeout=timeout, return_when="FIRST_COMPLETED"
        )
        stopper.cancel()
        if reader in done:
            if reader.exception() is not None:
                exc = reader.exception()
                tailer.error = f"{type(exc).__name__}: {exc}"[:300]
            return
        reader.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reader
        if not stop.is_set():
            tailer.restarts += 1  # stopped and resumed from its last offset


# ---- measurements


def judge(
    hosted: bool,
    p95: float | None,
    complete: bool,
    max_events: int | None,
    max_bytes: int | None,
    max_carried: int | None,
) -> dict[str, str]:
    """R5, R6 and R11 against the plan's bounds (10% of the history limits, p95 <= 1 s
    with every tailer complete, 50% of the payload limit). A missing value fails."""

    def under(value: int | None, bound: float) -> str:
        return "pass" if value is not None and value < bound else "fail"

    history = (
        "pass"
        if under(max_events, LIMIT_EVENTS * 0.1) == under(max_bytes, LIMIT_BYTES * 0.1) == "pass"
        else "fail"
    )
    return {
        "R5": history if hosted else "n/a",
        "R6": "pass" if p95 is not None and p95 <= 1000 and complete else "fail",
        "R11": under(max_carried, LIMIT_PAYLOAD * 0.5) if hosted else "n/a",
    }


def say(message: str) -> None:
    print(f"[load] {message}", file=sys.stderr, flush=True)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=SPIKE).stdout.strip()


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="load")
    parser.add_argument("option", choices=sorted(OPTIONS))
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--tailers", type=int, default=3)
    parser.add_argument("--label", default="run")
    args = parser.parse_args(argv)
    option = OPTIONS[args.option]
    say("building transport")
    transport = await option.build(600.0)
    say("transport ready")
    client = await Client.connect(ADDRESS)
    agents = Agents(transport)
    worker = Worker(
        client, task_queue=LOAD_QUEUE, workflows=[LoadAgentWorkflow], activities=[agents.publish]
    )
    run_id = uuid.uuid4().hex[:8]
    wfs = [f"load-{run_id}-a{i}" for i in range(args.agents)]
    tailers = [Tailer(wf, killable=(j == 0)) for wf in wfs for j in range(args.tailers)]
    stop = asyncio.Event()
    samples: list[dict[str, Any]] = []
    stats_stop = threading.Event()
    running = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, check=False
    ).stdout.split()
    wanted = ("pmspike76-db-1", "pmspike76-temporal-1")
    names = [n for n in wanted if n in running]
    sampler = threading.Thread(target=_sampler, args=(names, samples, stats_stop), daemon=True)
    began = time.monotonic()
    handles: list[Any] = []
    tasks: list[asyncio.Task[None]] = []
    agent_errors: list[str] = []
    results: list[AgentResult] = []
    latest: dict[str, int] = {wf: 0 for wf in wfs}
    try:
        async with worker:
            sampler.start()
            say("worker up; starting tailers")
            tasks = [asyncio.create_task(tail(transport, tl, stop)) for tl in tailers]
            for wf in wfs:
                handles.append(
                    await client.start_workflow(
                        LoadAgentWorkflow.run,
                        AgentInput(wf, args.seconds),
                        id=f"agent-{wf}",
                        task_queue=LOAD_QUEUE,
                        execution_timeout=timedelta(seconds=args.seconds + 180),  # F64
                    )
                )
            say(f"publishing for {args.seconds:.0f} s")
            for outcome in await asyncio.gather(
                *(h.result() for h in handles), return_exceptions=True
            ):
                if isinstance(outcome, BaseException):
                    agent_errors.append(f"{type(outcome).__name__}: {outcome}"[:300])
                else:
                    results.append(outcome)
            say("publishers done; tailers catching up")
            latest = {wf: await transport.latest(wf) or 0 for wf in wfs}
            catch_up = time.monotonic() + 60
            while time.monotonic() < catch_up and any(
                tl.last < latest[tl.workflow_id] and tl.error is None for tl in tailers
            ):
                await asyncio.sleep(0.5)
    finally:
        stop.set()
        say("stopping tailers")
        await asyncio.gather(*tasks, return_exceptions=True)
        stats_stop.set()
        for h in handles:  # never leave an agent running for the next run's worker (F64)
            with contextlib.suppress(Exception):
                await h.terminate("load run ended")
        await transport.close()
    elapsed = time.monotonic() - began
    runs: dict[str, Any] = {}  # Streams hosting runs; none remain (ADR-0009)

    latencies = [ms for tl in tailers for ms in tl.latency_ms]
    p95 = percentile(latencies, 0.95)
    all_runs = [r for rs in runs.values() for r in rs]
    max_events = max((r["events"] for r in all_runs), default=None)
    max_bytes = max((r["bytes"] for r in all_runs), default=None)
    max_carried = max((r["carried_input_bytes"] for r in all_runs), default=None)
    complete = all(tl.last == latest[tl.workflow_id] and tl.error is None for tl in tailers)
    judged = judge(option.hosted, p95, complete, max_events, max_bytes, max_carried)
    if agent_errors:
        judged = {k: "error" for k in judged}
    report = {
        "option": args.option,
        "label": args.label,
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain", "--", ".", ":!results")),
        "command": "uv run python load.py " + " ".join(argv),
        "finished": datetime.now(UTC).isoformat(timespec="seconds"),
        "params": {
            "seconds": args.seconds,
            "agents": args.agents,
            "tailers": args.tailers,
            "rate_per_s": RATE_PER_S,
            "batch_s": BATCH_S,
            "batch_max": BATCH_MAX,
        },
        "elapsed_s": round(elapsed, 1),
        "requirements": judged,
        "agent_errors": agent_errors,
        "published": sum(r.published for r in results),
        "batches": sum(r.batches for r in results),
        "publish_ms": {
            "p50": percentile([m for r in results for m in r.publish_ms], 0.5),
            "p95": percentile([m for r in results for m in r.publish_ms], 0.95),
        },
        "latency_ms": {
            "p50": percentile(latencies, 0.5),
            "p95": p95,
            "p99": percentile(latencies, 0.99),
            "max": max(latencies, default=None),
            "mean": statistics.fmean(latencies) if latencies else None,
        },
        "tailers": [
            {
                "workflow": tl.workflow_id,
                "killable": tl.killable,
                "shown": tl.shown,
                "last": tl.last,
                "latest": latest[tl.workflow_id],
                "restarts": tl.restarts,
                "expired": tl.expired,
                "error": tl.error,
            }
            for tl in tailers
        ],
        "complete": complete,
        "history": {
            "limits": {"events": LIMIT_EVENTS, "bytes": LIMIT_BYTES, "payload": LIMIT_PAYLOAD},
            "max_run_events": max_events,
            "max_run_bytes": max_bytes,
            "max_carried_bytes": max_carried,
            "runs": runs,
        },
        "containers": samples,
    }
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"load-{args.option}-{args.label}.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2) + "\n")
    tmp.replace(out)  # never a half-written results file (F78)
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("option", "label", "requirements", "published", "latency_ms", "complete")
            }
        )
    )
    print(
        f"history: max events {max_events}, max bytes {max_bytes}, "
        f"max carried {max_carried} -> {out}"
    )
    return 1 if agent_errors else 0


def _sampler(names: list[str], samples: list[dict[str, Any]], stop: Any) -> None:
    while not stop.is_set():
        out = subprocess.run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}",
                *names,
            ],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        for line in out.splitlines():
            parts = line.split("|")
            if len(parts) == 3:
                samples.append(
                    {
                        "t": round(time.time(), 1),
                        "name": parts[0],
                        "cpu": float(parts[1].rstrip("%") or 0),
                        "mem": parts[2].split(" / ")[0],
                    }
                )
        stop.wait(10)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
