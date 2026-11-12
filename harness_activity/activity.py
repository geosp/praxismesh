"""`run_harness_turn`: one bounded harness invocation (RFC Phase 1: run_harness_turn).

1. Refuse a turn for another template version (retryable), then record the attempt.
2. Restore: the newest checkpoint (by turn, attempt, seq), truncating the session
   to its position; or, with no checkpoint, start fresh from the task's inputs.
3. Run, configured only from the template, with heartbeats. Before every model
   call: check the budget, stop if a newer attempt exists, take a checkpoint.
4. Finish: a final checkpoint (with the finish report), outputs as `audit` blobs,
   the attempt row, and a small `TurnOutcome`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import socket
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from agents.extensions.memory.sqlalchemy_session import SQLAlchemySession
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio import activity

from common.blob_store import BlobStore
from common.errors import TemplateVersionUnavailable
from common.observability import log_context
from common.observability.metrics import (
    CHECKPOINT_BYTES,
    CHECKPOINT_SECONDS,
    TOKENS,
    TOOL_CALLS,
)
from common.persistence.repositories import (
    AttemptRepository,
    Checkpoint,
    CheckpointRepository,
    TaskRepository,
)
from common.schemas import Artifact, BlobRef, TurnInput, TurnOutcome
from harness_activity import workspace as ws
from harness_activity.config import build_config
from harness_activity.runner import HarnessRunner, RunResult, StopRun, Usage
from registry.loader import Registry

log = logging.getLogger("praxis.harness")
CONTINUE_MESSAGE = "Continue the task from where it stopped."
DEFAULT_HEARTBEAT_TIMEOUT = timedelta(seconds=30)


@dataclass
class Progress:
    """Cumulative over the attempts of one turn (RFC: lost attempts count)."""

    tokens_in: int = 0
    tokens_out: int = 0
    tool_calls: int = 0
    inner_turns: int = 0
    checkpoint_id: str | None = None


def worker_identity(template: str) -> str:
    return f"{socket.gethostname()}@{os.getpid()}/{template}"


class HarnessActivities:
    def __init__(
        self,
        registry: Registry,
        engine: AsyncEngine,
        blobs: BlobStore,
        runner: HarnessRunner,
        scratch: Path,
        identity: str,
    ) -> None:
        self.registry = registry
        self.engine = engine
        self.blobs = blobs
        self.runner = runner
        self.scratch = scratch
        self.identity = identity
        self.tasks = TaskRepository(engine)
        self.attempts = AttemptRepository(engine)
        self.checkpoints = CheckpointRepository(engine)

    @activity.defn(name="run_harness_turn")
    async def run_harness_turn(self, turn: TurnInput) -> TurnOutcome:
        loaded = self.registry.templates.get(turn.template)
        if loaded is None or loaded.hash != turn.template_hash:
            raise TemplateVersionUnavailable(
                f"this worker runs {loaded.template.ref if loaded else 'no'} "
                f"{turn.template}, not version {turn.template_version} of the task"
            )
        info = activity.info()
        attempt = info.attempt
        with log_context(
            task_id=turn.task_id,
            workflow_id=info.workflow_id,
            turn=turn.turn,
            attempt=attempt,
            worker=self.identity,
        ):
            await self.attempts.start(turn.task_id, turn.turn, attempt, self.identity)
            prior = Progress(**(info.heartbeat_details[0] if info.heartbeat_details else {}))
            workdir = self.scratch / turn.task_id / f"{turn.turn}-{attempt}-{uuid.uuid4().hex[:8]}"
            try:
                return await self._run(turn, attempt, prior, workdir, loaded.template.ref)
            finally:
                shutil.rmtree(workdir, ignore_errors=True)

    async def _run(
        self, turn: TurnInput, attempt: int, prior: Progress, workdir: Path, template_ref: str
    ) -> TurnOutcome:
        loaded = self.registry.templates[turn.template]
        config = build_config(self.registry, loaded, turn.task_id)
        session = SQLAlchemySession(turn.task_id, engine=self.engine)
        progress = Progress(**asdict(prior))
        seq = 0

        latest = await self.checkpoints.latest(turn.task_id)
        if latest is not None:
            ws.unpack(await self.blobs.get(latest.workspace_ref), workdir)
            items = await session.get_items()
            for _ in range(len(items) - latest.session_position):
                await session.pop_item()
            if latest.finish is not None:  # lost after finish_task: go straight to finish
                result = RunResult(
                    latest.finish["status"],
                    Usage(),
                    summary=latest.finish.get("summary", ""),
                    questions=latest.finish.get("questions", []),
                )
                return await self._finish(turn, attempt, progress, workdir, result, template_ref)
            input_text = CONTINUE_MESSAGE
        else:
            await session.clear_session()
            input_text = await self._fresh_start(turn.task_id, workdir)

        async def checkpoint(finish: dict[str, Any] | None = None) -> None:
            nonlocal seq
            started = time.monotonic()
            data = await asyncio.to_thread(ws.pack, workdir)
            ref = await self.blobs.put(data, content_type="application/gzip", retention="task")
            position = len(await session.get_items())
            cp_id = f"{turn.task_id}:{turn.turn}:{attempt}:{seq}"
            await self.checkpoints.insert(
                Checkpoint(
                    cp_id,
                    turn.task_id,
                    turn.turn,
                    attempt,
                    seq,
                    turn.task_id,
                    position,
                    ref,
                    finish,
                )
            )
            seq += 1
            progress.checkpoint_id = cp_id
            CHECKPOINT_BYTES.observe(len(data))
            CHECKPOINT_SECONDS.observe(time.monotonic() - started)

        base = Progress(**asdict(progress))

        async def before_model_call(usage: Usage) -> None:
            progress.tokens_in = base.tokens_in + usage.tokens_in
            progress.tokens_out = base.tokens_out + usage.tokens_out
            progress.tool_calls = base.tool_calls + usage.tool_calls
            progress.inner_turns = base.inner_turns + usage.inner_turns
            if await self.attempts.newer_attempt_exists(turn.task_id, turn.turn, attempt):
                raise StopRun("a newer attempt of this turn is running")
            await checkpoint()
            if usage.tokens_in + usage.tokens_out >= turn.remaining_tokens:
                raise StopRun("token budget for the task is used up")

        heartbeat = asyncio.create_task(self._heartbeat(progress))
        try:
            result = await self.runner.run(config, workdir, session, input_text, before_model_call)
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
        progress.tokens_in = base.tokens_in + result.usage.tokens_in
        progress.tokens_out = base.tokens_out + result.usage.tokens_out
        progress.tool_calls = base.tool_calls + result.usage.tool_calls
        progress.inner_turns = base.inner_turns + result.usage.inner_turns
        TOKENS.labels(template=template_ref, direction="in").inc(result.usage.tokens_in)
        TOKENS.labels(template=template_ref, direction="out").inc(result.usage.tokens_out)
        TOOL_CALLS.labels(template=template_ref, tool="any").inc(result.usage.tool_calls)
        finish = (
            {
                "status": result.status,
                "summary": result.summary,
                "questions": result.questions or [],
            }
            if result.status in ("done", "needs_input")
            else None
        )
        await checkpoint(finish)
        return await self._finish(turn, attempt, progress, workdir, result, template_ref)

    async def _fresh_start(self, task_id: str, workdir: Path) -> str:
        row = await self.tasks.get(task_id)
        if row is None:
            raise RuntimeError(f"task {task_id} is not recorded")
        workdir.mkdir(parents=True, exist_ok=True)
        for name, ref_json in (row["input_refs"] or {}).items():
            data = await self.blobs.get(BlobRef.model_validate(ref_json))
            (workdir / name).write_bytes(data)
        return (await self.blobs.get(BlobRef.model_validate(row["instructions_ref"]))).decode()

    async def _finish(
        self,
        turn: TurnInput,
        attempt: int,
        progress: Progress,
        workdir: Path,
        result: RunResult,
        template_ref: str,
    ) -> TurnOutcome:
        outputs: list[Artifact] = []
        if result.status == "done":
            row = await self.tasks.get(turn.task_id)
            for path in (row or {}).get("outputs") or []:
                target = workdir / path
                if target.is_file():
                    ref = await self.blobs.put(target.read_bytes(), retention="audit")
                    outputs.append(Artifact(path=path, ref=ref))
        await self.attempts.finish(
            turn.task_id,
            turn.turn,
            attempt,
            outcome=result.status,
            tokens_in=progress.tokens_in,
            tokens_out=progress.tokens_out,
            tool_calls=progress.tool_calls,
            failure_category="model_behavior" if result.error else None,
        )
        log.info(
            "harness turn finished",
            extra={"fields": {"status": result.status, "template": template_ref}},
        )
        return TurnOutcome(
            status=result.status,
            checkpoint_id=progress.checkpoint_id,
            tokens_in=progress.tokens_in,
            tokens_out=progress.tokens_out,
            tool_calls=progress.tool_calls,
            inner_turns=progress.inner_turns,
            attempts=attempt,
            summary=result.summary[:2000],
            questions=result.questions or [],
            outputs=outputs,
            error=result.error,
        )

    async def _heartbeat(self, progress: Progress) -> None:
        timeout = activity.info().heartbeat_timeout or DEFAULT_HEARTBEAT_TIMEOUT
        interval = max(1.0, timeout.total_seconds() / 3)
        while True:
            activity.heartbeat(asdict(progress))
            await asyncio.sleep(interval)
