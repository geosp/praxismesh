"""`make benchmark`: run the agent benchmark through TaskWorkflow on the configured
model and record the results (plan §8 benchmark rule; spec quality/agent-benchmarks).

    make benchmark                          # needs VLLM_BASE_URL in infra/.env
    make benchmark ARGS="--profile dsh"     # another profile (default: default)
    make benchmark ARGS="--baseline"        # record this run as the baseline
    make benchmark ARGS="--only fizzbuzz --out /tmp/smoke"   # a smoke run

The template is the profile's first allowed template. A `dsh` template gets a
paired DSH container of its own, started here (DSH migration plan D5). Each
task's final workspace is read from its last checkpoint snapshot and checked
deterministically. Results go to docs/benchmarks/<date>-<profile>.md and .json;
a run written elsewhere (--out) is not judged against the baseline. A run that
passes 2 or more fewer tasks than the baseline exceeds the regression limit
(owner decision, 2026-11-11: at most 1 task lost out of 10).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from common.blob_store.s3 import S3BlobStore
from common.persistence.repositories import (
    CheckpointRepository,
    RecordingBlobStore,
    make_engine,
)
from common.schemas import TaskResult
from harness_activity import workspace as ws
from orchestrator.submit import prepare_task, start_task
from registry.loader import LoadedTemplate, load_registry
from tests.benchmarks.agent_tasks.tasks import TASKS, Task, setup
from tests.support.dsh_container import build_image, start_container
from tests.support.workers import running_workers

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "benchmarks"
BASELINE = OUT / "baseline.json"
REGRESSION_LIMIT = 2  # failing this many more tasks than the baseline blocks closure
DSH_REQUIREMENTS = ROOT / "infra" / "dsh" / "requirements.txt"


def profile_template(profile: str) -> LoadedTemplate:
    """The template a task on `profile` resolves to when it names none."""
    return load_registry().resolve(profile)[1]


@contextmanager
def paired_dsh(loaded: LoadedTemplate) -> Iterator[None]:
    """For a `dsh` template, a DSH container for the in-process worker to pair
    with, as Compose pairs `worker-dsh-a` with `dsh-a`; otherwise nothing."""
    if loaded.template.harness != "dsh":
        yield
        return
    print("building and starting a DSH container", flush=True)
    container = start_container(build_image())
    os.environ["DSH_CONTROL"] = str(container.control)
    try:
        yield
    finally:
        os.environ.pop("DSH_CONTROL", None)
        container.stop()


def harness_label(loaded: LoadedTemplate) -> str:
    if loaded.template.harness == "dsh":
        pins = dict(
            line.split("==", 1)
            for line in DSH_REQUIREMENTS.read_text().splitlines()
            if "==" in line and not line.lstrip().startswith("#")
        )
        sdk = "deepseek-harness-sdk"
        return f"{sdk} {pins[sdk].split()[0]}"
    return f"openai-agents {importlib.metadata.version('openai-agents')}"


async def run_one(task: Task, client: Any, scratch: Path, profile: str) -> dict[str, Any]:
    inputs = scratch / "inputs" / task.id
    setup(task, inputs)
    engine = make_engine()
    s3 = S3BlobStore.from_env()
    await s3.ensure_bucket()
    start = await prepare_task(
        {
            "profile": profile,
            "instructions": task.prompt,
            "input_files": [str(p) for p in sorted(inputs.iterdir())],
        },
        load_registry(),
        RecordingBlobStore(s3, engine),
        base_dir=inputs,
    )
    began = time.monotonic()
    handle = await start_task(client, start)
    result: TaskResult | None
    status: str
    reason: str | None
    try:
        result = TaskResult.model_validate(await handle.result())
        status, reason = result.status, result.failure_reason
    except Exception as e:  # a failed Workflow still has checkpoints to check
        result, status, reason = None, "error", f"{type(e).__name__}: {e}"[:300]
    seconds = round(time.monotonic() - began, 1)
    final = scratch / "final" / task.id
    latest = await CheckpointRepository(engine).latest(start.task_id)
    if latest is not None:
        ws.unpack(await s3.get(latest.workspace_ref), final)
        passed, check = task.check(final)
    else:
        passed, check = False, "no checkpoint"
    async with engine.connect() as conn:
        tool_calls = (
            await conn.execute(
                text("SELECT COALESCE(sum(tool_calls), 0) FROM task_attempts WHERE task_id = :t"),
                {"t": start.task_id},
            )
        ).scalar_one()
    await engine.dispose()
    return {
        "task": task.id,
        "task_id": start.task_id,
        "passed": passed,
        "check": check,
        "status": status,
        "failure_reason": reason,
        "turns": result.turns if result else None,
        "attempts": result.attempts if result else None,
        "inner_turns": result.inner_turns if result else None,
        "tool_calls": int(tool_calls),
        "tokens_in": result.tokens_in if result else None,
        "tokens_out": result.tokens_out if result else None,
        "seconds": seconds,
    }


def environment(profile: str, loaded: LoadedTemplate) -> dict[str, Any]:
    prompt = (ROOT / "registry" / loaded.template.system_prompt).read_bytes()
    return {
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "profile": profile,
        "template": loaded.template.ref,
        "template_hash": loaded.hash,
        "model": loaded.template.model,
        "harness": harness_label(loaded),
        "prompt_hash": "sha256:" + hashlib.sha256(prompt).hexdigest(),
    }


def markdown(env: dict[str, Any], rows: list[dict[str, Any]], verdict: str) -> str:
    passed = sum(r["passed"] for r in rows)
    lines = [
        f"# Agent benchmark: {env['profile']} ({env['template']}), {env['date']}",
        "",
        f"**Passed {passed} of {len(rows)}.** {verdict}",
        "",
        "| Item | Value |",
        "|---|---|",
        *(f"| {k} | `{v}` |" for k, v in env.items() if k != "date"),
        "| Model endpoint | the DGX Spark endpoint (vLLM) |",
        "",
        "| Task | Result | Check | Turns | Inner turns | Attempts | Tool calls | Tokens in "
        "| Tokens out | Seconds |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['task']} | {'pass' if r['passed'] else 'FAIL'} | {r['check']} | {r['turns']} "
            f"| {r.get('inner_turns')} | {r['attempts']} | {r['tool_calls']} "
            f"| {r['tokens_in']} | {r['tokens_out']} | {r['seconds']} |"
        )
    return "\n".join(lines) + "\n"


def verdict_for(passed: int, make_baseline: bool, judged: bool = True) -> str:
    if make_baseline:
        return "Recorded as the baseline (docs/benchmarks/baseline.json)."
    if not judged:
        return "Not judged against the baseline (written outside docs/benchmarks)."
    if not BASELINE.exists():
        return "No baseline recorded yet."
    base = json.loads(BASELINE.read_text())["passed"]
    lost = base - passed
    if lost >= REGRESSION_LIMIT:
        return f"**Regression limit exceeded:** {lost} fewer than the baseline ({base})."
    return f"Within the regression limit (baseline {base})."


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="benchmark")
    parser.add_argument("--baseline", action="store_true", help="record as the baseline")
    parser.add_argument("--only", nargs="*", help="task IDs to run (default: all)")
    parser.add_argument("--profile", default="default", help="agent profile (default: default)")
    parser.add_argument(
        "--out", type=Path, default=OUT, help="results directory (default: docs/benchmarks)"
    )
    args = parser.parse_args(argv)
    judged = args.out.resolve() == OUT.resolve()
    if args.baseline and not judged:
        parser.error("--baseline records into docs/benchmarks; drop --out")
    loaded = profile_template(args.profile)
    if not os.environ.get("VLLM_BASE_URL"):
        print("error: VLLM_BASE_URL is not set; the benchmark needs a real model", file=sys.stderr)
        return 2
    tasks = [t for t in TASKS if not args.only or t.id in args.only]
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        with paired_dsh(loaded):
            async with running_workers(scratch / "workers", loaded.template.name) as client:
                for task in tasks:
                    row = await run_one(task, client, scratch, args.profile)
                    rows.append(row)
                    mark = "pass" if row["passed"] else "FAIL"
                    print(
                        f"{row['task']:20} {mark}  turns={row['turns']} "
                        f"inner={row['inner_turns']} tools={row['tool_calls']} "
                        f"in={row['tokens_in']} {row['seconds']}s  {row['check']}",
                        flush=True,
                    )
    env = environment(args.profile, loaded)
    passed = sum(r["passed"] for r in rows)
    verdict = verdict_for(passed, args.baseline, judged)
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"{env['date']}-{args.profile}"
    stem.with_suffix(".md").write_text(markdown(env, rows, verdict))
    stem.with_suffix(".json").write_text(
        json.dumps({**env, "passed": passed, "rows": rows}, indent=2) + "\n"
    )
    if args.baseline:
        BASELINE.write_text(
            json.dumps(
                {**env, "passed": passed, "results": stem.with_suffix(".json").name}, indent=2
            )
            + "\n"
        )
    print(f"passed {passed} of {len(rows)}. {verdict}")
    return 1 if "exceeded" in verdict else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
