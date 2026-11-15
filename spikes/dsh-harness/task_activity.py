"""Isolated DSH Activity implementation, never registered by production workers."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import yaml
from accounting_boundary import FixtureProvider
from preflight import environment_digest
from recovery_boundary import ToolExecutor
from recovery_store import Authority, capture_pair, restore_pair
from run_probe import (
    HERE,
    ROOT,
    local_provider,
    run_manifest,
    runtime_identity,
    save_manifest,
    stage_inputs,
)
from run_recovery import docker, recovery_command, stop_owned_attempt
from task_boundary import TaskBoundary
from task_completion import Completion, turn_outcome
from temporalio import activity
from temporalio.exceptions import ApplicationError

from common.persistence.repositories import AttemptRepository, TaskRepository
from common.schemas import Artifact, BlobRef, TurnInput, TurnOutcome
from harness_activity.activity import CONTINUE_MESSAGE

SHOP_GRANT = tuple(
    yaml.safe_load((ROOT / "registry/mcp/sample-shop.yaml").read_text())["tools_allowed"]
)
CLI_GRANT = yaml.safe_load((ROOT / "registry/templates/local-default.yaml").read_text())[
    "cli_tools"
]
PRODUCTION_PROMPT = (ROOT / "registry/prompts/local-default.md").read_text()
SKILL_PLUGINS = """    - id: praxis-skills
      name: '@deepseek-ai/dsh-skill'
    - id: praxis-skill-filesystem
      name: '@deepseek-ai/dsh-skill-filesystem'
      config:
        includeDefaultRoots: false
        customSkillDirs: [/opt/granted-skills]
        watch: false
    - id: praxis-tool-skill
      name: '@deepseek-ai/dsh-tool-skill'
    - id: praxis-recovery
"""
# Smaller than the Phase 01 probe defaults (1g, 2 CPUs) to protect the host.
TASK_LIMITS = {"memory": "512m", "cpus": "1"}
HOST_IDENTITY = runtime_identity(HERE, ROOT / "registry/skills/order-desk")


def scripted_response(case: str, temporal_attempt: int):
    def respond(request: dict, number: int) -> dict:
        faults = {
            "retry-model": "fixture unavailable before generation",
            "retry-protocol": "fixture malformed stream before generation",
            "retry-infrastructure": "fixture disconnect before generation",
            "bad-request": "fixture rejected input",
        }
        if case in faults and (temporal_attempt == 1 or case == "bad-request"):
            return {"fault": faults[case]}
        if case == "plain-text":
            return {"message": {"role": "assistant", "content": '{"status":"succeeded"}'}}
        args = {"status": "done", "summary": "Controlled fixture completed.", "questions": None}
        if case == "needs-input":
            args.update(
                status="needs_input",
                summary="Fixture needs an owner choice.",
                questions=["Which fixture value should be used?"],
            )
        if number == 1 or case == "inner-limit":
            if case in ("invalid-status", "inner-limit"):
                args["status"] = "succeeded"
            elif case == "invalid-payload":
                args["summary"] = {"invalid": "object"}
            elif case == "invalid-reference":
                args["artifacts"] = [{"path": "../escape", "ref": {"checksum": "bad"}}]
        return {
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"task-call-{number}",
                        "type": "function",
                        "function": {
                            "name": "mcp__task__finish_task",
                            "arguments": json.dumps(args),
                        },
                    }
                ],
            }
        }

    return respond


class NativeFailure(RuntimeError):
    def __init__(self, category: str, record: dict, retryable: bool):
        super().__init__(category)
        self.category, self.record, self.retryable = category, record, retryable


def native_turn(
    shared: Path,
    case: str,
    turn: TurnInput,
    temporal_attempt: int,
    remaining_tokens: int,
    inputs: dict[str, bytes],
    instructions: str,
    image: str,
    cancel: threading.Event,
) -> tuple[dict | None, dict, Path]:
    name = "praxis-dsh-task-" + uuid.uuid4().hex[:12]
    deadline_seconds = min(600, turn.remaining_wall_time.total_seconds())
    manifest = run_manifest(case, name, deadline_seconds, image)
    if any(manifest[key] != HOST_IDENTITY[key] for key in HOST_IDENTITY):
        raise RuntimeError("blocked: host source changed after controller import")
    manifest.update(
        session="task",
        task_id=turn.task_id,
        outer_turn=turn.turn,
        activity_attempt=temporal_attempt,
        task_token_ceiling=remaining_tokens,
        model_step_ceiling=2 if case == "inner-limit" else 8,
        task_kind="isolated DSH implementation of run_harness_turn on a unique queue",
        stop_trigger="native return, Activity cancellation, or monotonic turn deadline",
        phase02_stop_oracle_pending=False,
        container_limits=TASK_LIMITS,
    )
    shared.mkdir(parents=True, exist_ok=True)
    authority = Authority(shared / "authority.sqlite")
    lease = authority.claim()
    output = HERE / ".runs"
    benchmark = case == "benchmark"
    if benchmark:
        from bench_tools import BenchTools

        completion = BenchTools(
            output / name / "state/workspace", name, turn.task_id, list(SHOP_GRANT)
        )
    else:
        completion = Completion(shared / "unused-host-workspace")
    tools = completion.catalog()
    composition = (
        (HERE / "recovery-composition.yaml")
        .read_text()
        .replace("serverName: recovery", "serverName: task")
        .replace(
            "        cwd: /run/workspace\n",
            "        env:\n          PRAXIS_SPIKE_TASK_TOOLS: '1'\n        cwd: /run/workspace\n",
        )
    )
    if benchmark:
        composition = composition.replace("    - id: praxis-recovery\n", SKILL_PLUGINS)
    publication = authority.publication()
    restored = publication is not None
    task_input = {"resume": restored, "instructions": instructions}
    if benchmark:
        # Production passes the template prompt as agent instructions every turn
        # and CONTINUE_MESSAGE on resume; DSH receives the prompt as a trusted
        # first-turn block in its restored conversation instead.
        task_input.update(
            operating_instructions=PRODUCTION_PROMPT,
            instructions=CONTINUE_MESSAGE if restored else instructions,
        )
        manifest.update(
            task_kind="R8 benchmark task through the isolated DSH run_harness_turn",
            granted_tools=sorted(t["name"] for t in tools),
            cli_tools=CLI_GRANT,
            prompt_sha256=hashlib.sha256(PRODUCTION_PROMPT.encode()).hexdigest(),
        )
    additions = {
        "task-composition.yaml": composition.encode(),
        "task-tools.json": json.dumps(tools, sort_keys=True).encode(),
        "task-input.json": json.dumps(task_input, sort_keys=True).encode(),
    }
    manifest["trusted_additions"] = {k: hashlib.sha256(v).hexdigest() for k, v in additions.items()}
    output.mkdir(exist_ok=True)
    manifest_hash = save_manifest(output / (name + "-manifest.json"), manifest)
    scratch = output / name
    scratch.mkdir()
    record = {
        "case": case,
        "task_id": turn.task_id,
        "turn": turn.turn,
        "attempt": temporal_attempt,
        "lease": lease,
        "manifest_sha256": manifest_hash,
        "exit": 1,
        "restored": restored,
    }
    gateway = executor = provider = process = log = None
    started = False
    stop_trigger = None
    finish = None
    failure = None
    try:
        stage_inputs(scratch, manifest)
        for filename, content in additions.items():
            (scratch / "code" / filename).write_bytes(content)
        shutil.copytree(
            HERE / ".venv/lib/python3.11/site-packages",
            scratch / "environment",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            symlinks=True,
        )
        if environment_digest(scratch / "environment") != manifest["environment_sha256"]:
            raise RuntimeError("blocked: dependency snapshot changed during staging")
        state = scratch / "state"
        if restored:
            _, payload = authority.restore()
            restore_pair(payload, state)
        else:
            (state / "home").mkdir(parents=True)
            (state / "workspace").mkdir()
            for filename, content in inputs.items():
                if Path(filename).is_absolute() or ".." in Path(filename).parts:
                    raise ValueError("input outside fixture workspace")
                path = state / "workspace" / filename
                if path.is_absolute() and state not in path.parents:
                    raise ValueError("input outside fixture workspace")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        (state / "ipc").mkdir()

        def checkpoint():
            docker("pause", name)
            try:
                payload = capture_pair(state, None)
                record["checkpoint_sha256"] = authority.acknowledge(
                    lease, payload, {"finish": None}
                )
            finally:
                docker("unpause", name)

        upstream, api_key = local_provider() if benchmark else (None, "")
        if not benchmark:
            provider = FixtureProvider(case, scripted_response(case, temporal_attempt))
        gateway = TaskBoundary(
            state / "ipc/model.sock",
            name,
            temporal_attempt,
            {"mcp__task__" + t["name"] for t in tools} | ({"skill"} if benchmark else set()),
            completion,
            budget=remaining_tokens,
            steps=manifest["model_step_ceiling"],
            fixture=provider,
            upstream=upstream,
            api_key=api_key,
            checkpoint=checkpoint,
        )
        executor = ToolExecutor(
            state,
            authority,
            lease,
            "unused",
            dispatcher=completion.dispatch,
            allowed_names={t["name"] for t in tools},
        )
        if provider is not None:
            provider.start()
        gateway.start()
        executor.start()
        started = True
        log = (scratch / "candidate.log").open("w+")
        command = recovery_command(name, state, "start", image, **TASK_LIMITS)
        command[-2:] = ["/opt/spike/task_driver.py", "controlled"]
        process = subprocess.Popen(command, stdout=log, stderr=log)
        until = time.monotonic() + deadline_seconds
        while process.poll() is None:
            if cancel.is_set() or time.monotonic() >= until:
                stop_trigger = time.monotonic()
                docker("kill", "--signal=TERM", name)
                process.wait(timeout=5)
                raise RuntimeError(
                    "Activity cancelled" if cancel.is_set() else "turn deadline exceeded"
                )
            time.sleep(0.02)
        stop_trigger = time.monotonic()
        result_path = state / "candidate-result.json"
        record["candidate"] = json.loads(result_path.read_text()) if result_path.exists() else None
        finish = completion.report()
        record.update(
            finish=finish,
            model_requests=gateway.requests,
            ledger=gateway.ledger.records,
            totals=gateway.ledger.totals(),
            provider_dispatches=provider.dispatches if provider is not None else None,
            tool_entries=executor.entries,
            provider_fault=gateway.fault,
        )
        if process.returncode != 0 or record["candidate"] is None:
            failure = ("DshRuntimeFailure", True)
        elif record["totals"]["unknown_usage"]:
            failure = ("DshUsageUnknown", False)
        elif gateway.fault:
            bad_input = gateway.fault in ("fixture rejected input", "provider rejected input")
            failure = ("HarnessInputError" if bad_input else "DshProviderFailure", not bad_input)
        elif record["candidate"].get("error_type"):
            failure = ("DshProtocolFailure", True)
        elif (
            not finish
            and record["candidate"].get("finish_reason") == "error"
            and not any(
                item.get("denial") in ("model-step limit", "token budget")
                for item in gateway.ledger.records
            )
        ):
            failure = ("DshModelFailure", True)
        else:
            record["exit"] = 0
        primary = (record["candidate"] or {}).get("primary_usage", [])
        if not record["totals"]["unknown_usage"]:
            expected = (record["totals"]["input_tokens"], record["totals"]["output_tokens"])
            observed = tuple(
                sum(item[key] for item in primary) for key in ("input_tokens", "output_tokens")
            )
            physical = record["totals"]["physical_dispatches"]
            dispatched = (
                len(provider.dispatches)
                if provider is not None
                else sum(1 for item in gateway.ledger.records if item["dispatched"])
            )
            if observed != expected or dispatched != physical:
                failure = ("DshAccountingFailure", False)
                record["exit"] = 1
            else:
                record["candidate_usage_reconciled"] = True
    except Exception as error:
        record.update(error_type=type(error).__name__)
        failure = ("DshRuntimeFailure", True)
    finally:
        if started:
            record["cleanup"] = stop_owned_attempt(
                name, gateway, executor, process, log, trigger=stop_trigger
            )
        if not record.get("cleanup", {}).get("cleanup_ok"):
            record["exit"] = 1
            failure = ("DshCleanupFailure", False)
        if not failure:
            try:
                payload = capture_pair(scratch / "state", None)
                record["checkpoint_sha256"] = authority.acknowledge(
                    lease, payload, {"finish": finish}
                )
            except Exception as error:
                record.update(exit=1, checkpoint_error_type=type(error).__name__)
                failure = ("DshCheckpointFailure", False)
        if benchmark:
            completion.close()
        (output / (name + "-result.json")).write_text(json.dumps(record, indent=2) + "\n")
    if failure:
        raise NativeFailure(failure[0], record, failure[1])
    return finish, record, scratch / "state/workspace"


class TaskActivities:
    def __init__(self, engine, blobs, scratch: Path, image: str, case: str):
        self.tasks, self.attempts = TaskRepository(engine), AttemptRepository(engine)
        self.blobs, self.scratch, self.image, self.case = blobs, scratch, image, case
        self.records: list[dict] = []

    @activity.defn(name="run_harness_turn")
    async def run_harness_turn(self, turn: TurnInput) -> TurnOutcome:
        attempt = activity.info().attempt
        if attempt > 5:
            raise ApplicationError(
                "five real attempts exhausted", type="AttemptsExhausted", non_retryable=True
            )
        row = await self.tasks.get(turn.task_id)
        if row is None:
            raise ApplicationError(
                "fixture task missing", type="HarnessInputError", non_retryable=True
            )
        prior = [r for r in await self.attempts.list(turn.task_id) if r["turn"] == turn.turn]
        prior_in = sum(r["tokens_in"] for r in prior)
        prior_out = sum(r["tokens_out"] for r in prior)
        remaining = turn.remaining_tokens - prior_in - prior_out
        if remaining <= 0:
            return TurnOutcome(
                status="continue", tokens_in=prior_in, tokens_out=prior_out, attempts=attempt
            )
        inputs = {
            name: await self.blobs.get(BlobRef.model_validate(ref))
            for name, ref in (row["input_refs"] or {}).items()
        }
        instructions = (
            await self.blobs.get(BlobRef.model_validate(row["instructions_ref"]))
        ).decode()
        await self.attempts.start(turn.task_id, turn.turn, attempt, "isolated-dsh-spike")
        cancel = threading.Event()
        task = asyncio.create_task(
            asyncio.to_thread(
                native_turn,
                self.scratch / turn.task_id,
                self.case,
                turn,
                attempt,
                remaining,
                inputs,
                instructions,
                self.image,
                cancel,
            )
        )
        try:
            while not task.done():
                activity.heartbeat(
                    {"attempts": attempt, "tokens_in": prior_in, "tokens_out": prior_out}
                )
                await asyncio.sleep(0.1)
            finish, record, workspace = task.result()
        except asyncio.CancelledError:
            cancel.set()
            with contextlib.suppress(Exception):
                await asyncio.shield(task)
            raise
        except NativeFailure as error:
            self.records.append(error.record)
            totals = error.record.get("totals", {})
            incoming, outgoing = totals.get("input_tokens") or 0, totals.get("output_tokens") or 0
            await self.attempts.finish(
                turn.task_id,
                turn.turn,
                attempt,
                outcome="failed",
                tokens_in=incoming,
                tokens_out=outgoing,
                tool_calls=0,
                failure_category=error.category,
            )
            raise ApplicationError(
                error.category,
                {
                    "tokens_in": prior_in + incoming,
                    "tokens_out": prior_out + outgoing,
                    "attempts": attempt,
                },
                type=error.category,
                non_retryable=not error.retryable,
            ) from error
        self.records.append(record)
        outputs = []
        if finish and finish["status"] == "done":
            for name in row["outputs"] or []:
                path = workspace / name
                if path.is_file():
                    ref = await self.blobs.put(path.read_bytes(), retention="audit")
                    if await self.blobs.get(ref) != path.read_bytes():
                        raise RuntimeError("artifact failed read-back")
                    outputs.append(Artifact(path=name, ref=ref))
        # Each attempt stages a ~200 MB dependency copy; keep only failed trees.
        # The acknowledged checkpoint lives in the shared authority, not here.
        attempt_tree = workspace.parent.parent
        if attempt_tree.parent == HERE / ".runs" and attempt_tree.name.startswith(
            "praxis-dsh-task-"
        ):
            shutil.rmtree(attempt_tree, ignore_errors=True)
        totals = record["totals"]
        tool_calls = sum(e["admitted"] for e in record["tool_entries"])
        await self.attempts.finish(
            turn.task_id,
            turn.turn,
            attempt,
            outcome=finish["status"] if finish else "continue",
            tokens_in=totals["input_tokens"],
            tokens_out=totals["output_tokens"],
            tool_calls=tool_calls,
        )
        cumulative = dict(
            totals,
            input_tokens=prior_in + totals["input_tokens"],
            output_tokens=prior_out + totals["output_tokens"],
        )
        result = turn_outcome(
            finish,
            cumulative,
            checkpoint=record["checkpoint_sha256"],
            tool_calls=tool_calls,
            outputs=outputs,
        )
        return result.model_copy(update={"attempts": attempt})
