"""Isolated DSH Activity implementation, never registered by production workers."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import stat
import subprocess
import threading
import time
import uuid
from pathlib import Path

import yaml
from accounting_boundary import FixtureProvider
from model_gateway import MAX_BODY
from preflight import environment_digest
from recovery_boundary import ToolExecutor
from recovery_store import (
    Authority,
    CheckpointLimit,
    Superseded,
    capture_pair,
    restore_pair,
)
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
from task_policy import (
    CLEANUP_GRACE_SECONDS,
    SKILL_BUNDLE,
    STALE_PHASE01,
    TURN_TIMEOUT_SECONDS,
    attempt_order,
    classify,
    prior_progress,
    progress,
    step_ceiling,
    task_inventory,
    validate_manifest,
)
from temporalio import activity
from temporalio.exceptions import ApplicationError

from common.persistence.repositories import AttemptRepository, TaskRepository
from common.schemas import Artifact, BlobRef, TurnInput, TurnOutcome
from harness_activity import skills
from harness_activity.activity import CONTINUE_MESSAGE, MAX_REAL_ATTEMPTS

SHOP_GRANT = tuple(
    yaml.safe_load((ROOT / "registry/mcp/sample-shop.yaml").read_text())["tools_allowed"]
)
CLI_GRANT = yaml.safe_load((ROOT / "registry/templates/local-default.yaml").read_text())[
    "cli_tools"
]
PRODUCTION_PROMPT = (ROOT / "registry/prompts/local-default.md").read_text()
# Production lists the template skill bundle in the instructions and the model
# reads it with read_file (harness_activity/runner.py); the paths are relative.
SKILL_INDEX = skills.index(
    SKILL_BUNDLE, Path("/workspace") / skills.SKILLS_DIR / SKILL_BUNDLE.name, Path("/workspace")
)
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


def remove_attempt_tree(path: Path) -> None:
    """Remove one disposable attempt tree, including its read-only skill mount."""
    if path.parent != HERE / ".runs" or not path.name.startswith("praxis-dsh-task-"):
        raise ValueError("refusing to remove a path outside disposable attempt trees")
    for item in [path, *path.rglob("*")]:
        if item.is_dir() and not item.is_symlink():
            item.chmod(item.stat().st_mode | stat.S_IRWXU)
    shutil.rmtree(path, ignore_errors=True)


def task_composition(benchmark: bool) -> str:
    # The task composition never enables DSH skill plugins or native file/shell
    # tools; the benchmark reaches the template skill through executor read_file.
    del benchmark
    return (
        (HERE / "recovery-composition.yaml")
        .read_text()
        .replace("serverName: recovery", "serverName: task")
        .replace(
            "        cwd: /run/workspace\n",
            "        env:\n          PRAXIS_SPIKE_TASK_TOOLS: '1'\n        cwd: /run/workspace\n",
        )
    )


def zero_totals() -> dict:
    return dict(
        ingress=0,
        physical_dispatches=0,
        denied_ingress=0,
        input_tokens=0,
        output_tokens=0,
        unknown_usage=0,
        logical_steps=0,
    )


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
    live: dict | None = None,
) -> tuple[dict | None, dict, Path]:
    name = "praxis-dsh-task-" + uuid.uuid4().hex[:12]
    benchmark = case == "benchmark"
    deadline_seconds = min(TURN_TIMEOUT_SECONDS, turn.remaining_wall_time.total_seconds())
    # Declared fixture override, like the bounds probes: a two-second deadline
    # measured from independent provider entry. It only ever shortens the turn.
    entry_deadline = 2.0 if case == "deadline" and temporal_attempt == 1 else None
    manifest = run_manifest(case, name, deadline_seconds, image)
    if any(manifest[key] != HOST_IDENTITY[key] for key in HOST_IDENTITY):
        raise RuntimeError("blocked: host source changed after controller import")
    for key in STALE_PHASE01:
        manifest.pop(key, None)
    order = attempt_order(turn.turn, temporal_attempt)
    manifest.update(
        session="task",
        task_id=turn.task_id,
        outer_turn=turn.turn,
        activity_attempt=temporal_attempt,
        attempt_order=order,
        task_token_ceiling=remaining_tokens,
        model_step_ceiling=step_ceiling(case),
        task_kind=(
            "R8 benchmark task through the isolated DSH run_harness_turn"
            if benchmark
            else "isolated DSH implementation of run_harness_turn on a unique queue"
        ),
        stop_trigger=(
            "native return, Activity cancellation or monotonic turn deadline; "
            "SIGTERM must stop the container within the cleanup grace"
        ),
        phase02_stop_oracle_pending=False,
        container_limits=TASK_LIMITS,
        auxiliary_inventory=task_inventory(benchmark),
        cli_tools=CLI_GRANT,
        fixture_entry_deadline_seconds=entry_deadline,
    )
    shared.mkdir(parents=True, exist_ok=True)
    authority = Authority(shared / "authority.sqlite")
    lease = authority.claim(order)  # Superseded when a newer attempt already owns it
    output = HERE / ".runs"
    output.mkdir(exist_ok=True)
    scratch = output / name
    record = {
        "case": case,
        "task_id": turn.task_id,
        "turn": turn.turn,
        "attempt": temporal_attempt,
        "lease": lease,
        "exit": 1,
    }
    if live is not None:
        live["lease"] = lease
    completion = gateway = executor = provider = process = log = None
    started = blocked = short_circuit = False
    stop_trigger = stop_reason = None
    finish = None
    failure = None
    try:
        if benchmark:
            from bench_tools import BenchTools

            completion = BenchTools(
                scratch / "state/workspace", name, turn.task_id, list(SHOP_GRANT)
            )
        else:
            completion = Completion(shared / "unused-host-workspace")
        tools = completion.catalog()
        publication = authority.publication()
        restored = publication is not None
        record["restored"] = restored
        task_input = {"resume": restored, "instructions": instructions}
        if benchmark:
            # Production passes the template prompt and skill index as agent
            # instructions every turn and CONTINUE_MESSAGE on resume; DSH receives
            # them as a trusted first-turn block in its restored conversation.
            task_input.update(
                operating_instructions=PRODUCTION_PROMPT + "\n\n" + SKILL_INDEX,
                instructions=CONTINUE_MESSAGE if restored else instructions,
            )
            manifest["prompt_sha256"] = hashlib.sha256(PRODUCTION_PROMPT.encode()).hexdigest()
            manifest["skill_index_sha256"] = hashlib.sha256(SKILL_INDEX.encode()).hexdigest()
        manifest["granted_tools"] = sorted(t["name"] for t in tools)
        additions = {
            "task-composition.yaml": task_composition(benchmark).encode(),
            "task-tools.json": json.dumps(tools, sort_keys=True).encode(),
            "task-input.json": json.dumps(task_input, sort_keys=True).encode(),
        }
        manifest["trusted_additions"] = {
            k: hashlib.sha256(v).hexdigest() for k, v in additions.items()
        }
        record["manifest_sha256"] = save_manifest(output / (name + "-manifest.json"), manifest)
        problems = validate_manifest(manifest)
        if problems:
            record["manifest_problems"] = problems
            raise RuntimeError("blocked: invalid run manifest")
        scratch.mkdir()
        if publication is not None and publication.get("finish") is not None:
            # Production parity (harness_activity/activity.py): an attempt lost
            # after its finish was acknowledged completes from that record. The
            # candidate is not started again, so no work can follow the finish.
            digest, payload = authority.restore()
            restore_pair(payload, scratch / "state")
            finish = publication["finish"]
            short_circuit = True
            record.update(
                exit=0,
                short_circuit="finish already acknowledged",
                finish=finish,
                checkpoint_sha256=digest,
                candidate=None,
                model_requests=[],
                ledger=[],
                provider_dispatches=[],
                tool_entries=[],
                totals=zero_totals(),
                settled={k: 0 for k in ("input_tokens", "output_tokens", "unknown_usage")},
                cleanup={"cleanup_ok": True, "container_started": False},
            )
            return finish, record, scratch / "state/workspace"
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
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        if benchmark:
            skills.mount(SKILL_BUNDLE, state / "workspace")
        (state / "ipc").mkdir()
        abort = threading.Event()

        def checkpoint(session_marker: str | None):
            # Barrier: the held request proves DSH's checkpoint policy flushed the
            # results before it; the paused container freezes the other writers.
            # The newest tool result must already be in durable session state.
            docker("pause", name)
            try:
                payload = capture_pair(
                    state, None, session_marker=session_marker, workspace_policy="production"
                )
                record["checkpoint_sha256"] = authority.acknowledge(
                    lease, payload, {"finish": None}
                )
            finally:
                try:
                    resumed = docker("unpause", name, check=False).returncode == 0
                except subprocess.TimeoutExpired:
                    resumed = False
                if not resumed:
                    record["unpause_failed"] = True
                    abort.set()

        upstream, api_key = local_provider() if benchmark else (None, "")
        if not benchmark:
            provider = FixtureProvider(
                case,
                scripted_response(case, temporal_attempt),
                stall_first=case in ("deadline", "cancel") and temporal_attempt == 1,
            )
        gateway = TaskBoundary(
            state / "ipc/model.sock",
            name,
            temporal_attempt,
            {"mcp__task__" + t["name"] for t in tools},
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
            max_request=MAX_BODY,  # the recovery probe's 4 KiB bound would refuse large writes
        )
        if live is not None:
            live.update(ledger=gateway.ledger, executor=executor, provider=provider)
        if provider is not None:
            provider.start()
        gateway.start()
        executor.start()
        log = (scratch / "candidate.log").open("w+")
        command = recovery_command(name, state, "start", image, **TASK_LIMITS)
        command[-2:] = ["/opt/spike/task_driver.py", "controlled"]
        process = subprocess.Popen(command, stdout=log, stderr=log)
        started = True
        until = time.monotonic() + deadline_seconds
        while process.poll() is None:
            if entry_deadline is not None and provider is not None and provider.entered.is_set():
                until = min(until, time.monotonic() + entry_deadline)
                entry_deadline = None
            if cancel.is_set() or abort.is_set() or time.monotonic() >= until:
                stop_reason = (
                    "cancelled"
                    if cancel.is_set()
                    else "checkpoint unpause failed"
                    if abort.is_set()
                    else "turn deadline exceeded"
                )
                stop_trigger = time.monotonic()
                docker("kill", "--signal=TERM", name, check=False)
                try:
                    process.wait(
                        timeout=max(0.0, CLEANUP_GRACE_SECONDS - (time.monotonic() - stop_trigger))
                    )
                    record["cooperative_stop"] = True
                except subprocess.TimeoutExpired:
                    record["cooperative_stop"] = False  # forced cleanup cannot pass R5
                break
            time.sleep(0.02)
        if stop_trigger is None:
            stop_trigger = time.monotonic()
        record["stop_reason"] = stop_reason
        result_path = state / "candidate-result.json"
        record["candidate"] = json.loads(result_path.read_text()) if result_path.exists() else None
        finish = completion.report()
        record["finish"] = finish
    except Superseded:
        record["error_type"] = "Superseded"
    except Exception as error:
        record["error_type"] = type(error).__name__
        blocked = str(error).startswith("blocked:")
        if blocked:
            record["error"] = str(error)
    finally:
        if not short_circuit:
            if started:
                record["cleanup"] = stop_owned_attempt(
                    name, gateway, executor, process, log, trigger=stop_trigger
                )
            else:
                # Nothing was launched, but host listeners may already be running.
                for resource in (gateway, executor):
                    if resource is not None:
                        try:
                            resource.close()
                        except Exception as error:
                            record.setdefault("close_errors", []).append(type(error).__name__)
                if log is not None:
                    log.close()
            # Copy what was observed on every path, including deadline, cancel,
            # crash and pre-launch failures; unknown usage is never written as 0.
            if gateway is not None:
                record.update(
                    model_requests=gateway.requests,
                    ledger=gateway.ledger.records,
                    totals=gateway.ledger.totals(),
                    settled=gateway.ledger.settled(),
                    provider_fault=gateway.fault,
                )
            if executor is not None:
                record["tool_entries"] = executor.entries
            if provider is not None:
                record["provider_dispatches"] = provider.dispatches
            failure = classify(
                blocked=blocked,
                started=started,
                cleanup_ok=record.get("cleanup", {}).get("cleanup_ok", not started),
                cooperative_stop=record.get("cooperative_stop"),
                settled=record.get("settled"),
                fault=record.get("provider_fault"),
                error_type=record.get("error_type"),
                stop_reason=stop_reason,
                returncode=process.returncode if process is not None else None,
                candidate=record.get("candidate"),
                finish=finish,
                denials=[r["denial"] for r in record.get("ledger", []) if r.get("denial")],
            )
            if failure is None:
                failure = reconcile(record, provider, gateway)
            if failure is None:
                last = next(
                    (
                        r["last_tool_call_id"]
                        for r in reversed(gateway.requests)
                        if r.get("last_tool_call_id")
                    ),
                    None,
                )
                try:
                    payload = capture_pair(
                        scratch / "state", None, session_marker=last, workspace_policy="production"
                    )
                    record["checkpoint_sha256"] = authority.acknowledge(
                        lease, payload, {"finish": finish}
                    )
                except CheckpointLimit:
                    record["checkpoint_error_type"] = "CheckpointLimit"
                    failure = ("DshCheckpointLimit", False)
                except Superseded:
                    record["checkpoint_error_type"] = "Superseded"
                    failure = ("Superseded", True)
                except Exception as error:
                    record["checkpoint_error_type"] = type(error).__name__
                    failure = ("DshCheckpointFailure", False)
            record["exit"] = 0 if failure is None else 1
            if failure is not None:
                record["failure_category"] = failure[0]
        if benchmark and completion is not None:
            completion.close()
        (output / (name + "-result.json")).write_text(json.dumps(record, indent=2) + "\n")
    if failure:
        raise NativeFailure(failure[0], record, failure[1])
    return finish, record, scratch / "state/workspace"


def reconcile(record: dict, provider, gateway) -> tuple[str, bool] | None:
    """Candidate-reported usage must match the trusted model-boundary ledger."""
    totals = record["totals"]
    primary = (record.get("candidate") or {}).get("primary_usage", [])
    expected = (totals["input_tokens"], totals["output_tokens"])
    observed = tuple(
        sum(item[key] for item in primary) for key in ("input_tokens", "output_tokens")
    )
    dispatched = (
        len(provider.dispatches)
        if provider is not None
        else sum(1 for item in gateway.ledger.records if item["dispatched"])
    )
    if observed != expected or dispatched != totals["physical_dispatches"]:
        return "DshAccountingFailure", False
    record["candidate_usage_reconciled"] = True
    return None


class TaskActivities:
    def __init__(self, engine, blobs, scratch: Path, image: str, case: str):
        self.tasks, self.attempts = TaskRepository(engine), AttemptRepository(engine)
        self.blobs, self.scratch, self.image, self.case = blobs, scratch, image, case
        self.records: list[dict] = []
        self.live: dict = {}

    def owns(self, task_id: str, lease: int | None) -> bool:
        path = self.scratch / task_id / "authority.sqlite"
        return lease is not None and path.exists() and Authority(path).owns(lease)

    @activity.defn(name="run_harness_turn")
    async def run_harness_turn(self, turn: TurnInput) -> TurnOutcome:
        info = activity.info()
        attempt = info.attempt
        rows = [r for r in await self.attempts.list(turn.task_id) if r["turn"] == turn.turn]
        prior = prior_progress(list(info.heartbeat_details or []), rows)
        if attempt > MAX_REAL_ATTEMPTS:
            # Production parity: report what the turn used, lost attempts included.
            await self.attempts.close_unfinished(
                turn.task_id,
                turn.turn,
                "lost_or_timed_out",
                outcome="lost",
                through_attempt=attempt,
            )
            raise ApplicationError(
                f"turn {turn.turn} was lost {MAX_REAL_ATTEMPTS} times",
                {**prior, "attempts": MAX_REAL_ATTEMPTS},
                type="AttemptsExhausted",
                non_retryable=True,
            )
        row = await self.tasks.get(turn.task_id)
        if row is None:
            raise ApplicationError(
                "fixture task missing", type="HarnessInputError", non_retryable=True
            )
        remaining = turn.remaining_tokens - prior["tokens_in"] - prior["tokens_out"]
        if remaining <= 0:
            return TurnOutcome(
                status="continue",
                tokens_in=prior["tokens_in"],
                tokens_out=prior["tokens_out"],
                attempts=attempt,
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
        live: dict = {}
        self.live = live

        def beat() -> dict:
            ledger, executor = live.get("ledger"), live.get("executor")
            admitted = sum(e["admitted"] for e in executor.entries) if executor else 0
            return progress(attempt, prior, ledger.settled() if ledger else None, admitted)

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
                live,
            )
        )
        try:
            while not task.done():
                activity.heartbeat(beat())
                await asyncio.sleep(0.1)
            finish, record, workspace = task.result()
            activity.heartbeat(beat())
        except asyncio.CancelledError:
            cancel.set()
            # Wait for the owned work to stop, even across repeated cancellation.
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            error = task.exception() if task.done() and not task.cancelled() else None
            record = error.record if isinstance(error, NativeFailure) else {}
            if record:
                self.records.append(record)
            if self.owns(turn.task_id, live.get("lease")):
                settled = record.get("settled") or {}
                await self.attempts.finish(
                    turn.task_id,
                    turn.turn,
                    attempt,
                    outcome="cancelled",
                    tokens_in=settled.get("input_tokens", 0),
                    tokens_out=settled.get("output_tokens", 0),
                    tool_calls=sum(e["admitted"] for e in record.get("tool_entries", [])),
                    failure_category="cancelled",
                )
            raise
        except Superseded as error:
            # A newer attempt owns the task: write no row, publication or artifact.
            raise ApplicationError(str(error), type="Superseded") from error
        except NativeFailure as error:
            record = error.record
            self.records.append(record)
            if not self.owns(turn.task_id, record.get("lease")):
                raise ApplicationError("superseded attempt", type="Superseded") from error
            settled = record.get("settled") or {}
            admitted = sum(e["admitted"] for e in record.get("tool_entries", []))
            await self.attempts.finish(
                turn.task_id,
                turn.turn,
                attempt,
                outcome="failed",
                tokens_in=settled.get("input_tokens", 0),
                tokens_out=settled.get("output_tokens", 0),
                tool_calls=admitted,
                failure_category=error.category,
            )
            if not error.retryable:
                await self.attempts.close_unfinished(
                    turn.task_id, turn.turn, error.category, through_attempt=attempt
                )
            raise ApplicationError(
                error.category,
                progress(attempt, prior, settled, admitted),
                type=error.category,
                non_retryable=not error.retryable,
            ) from error
        self.records.append(record)
        if self.case == "lost-after-finish" and attempt == 1:
            # Fault injection: the worker is lost after the finish checkpoint was
            # acknowledged, before Temporal records the Activity result. Like a
            # real loss, no attempt row is finished; usage survives in the heartbeat.
            raise ApplicationError("injected worker loss after finish acknowledgment")
        if not self.owns(turn.task_id, record["lease"]):
            raise ApplicationError("superseded attempt", type="Superseded")
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
        remove_attempt_tree(workspace.parent.parent)
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
            input_tokens=prior["tokens_in"] + totals["input_tokens"],
            output_tokens=prior["tokens_out"] + totals["output_tokens"],
        )
        result = turn_outcome(
            finish,
            cumulative,
            checkpoint=record["checkpoint_sha256"],
            tool_calls=tool_calls,
            outputs=outputs,
        )
        return result.model_copy(update={"attempts": attempt})
