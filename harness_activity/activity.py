"""`run_harness_turn`: one bounded harness invocation (RFC Phase 1: run_harness_turn).

1. Refuse a turn for another template version (retryable; refusals are not
   counted as attempts), then record the attempt.
2. Restore: the newest checkpoint (by turn, attempt, seq), truncating the session
   to its position; or, with no checkpoint, start fresh from the task's inputs.
3. Run, configured only from the template. Before every model call: check the
   task's token budget (including lost attempts), stop if a newer attempt
   exists, take a checkpoint.
4. Finish: a final checkpoint (with the finish report), outputs as `audit`
   artifacts, the attempt row, and a small `TurnOutcome`.

Heartbeats cover all of it, from the attempt row to the outcome, and carry the
live, cumulative usage of the turn (lost attempts included).
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import os
import shutil
import socket
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from agents.extensions.memory.sqlalchemy_session import SQLAlchemySession
from openai import BadRequestError
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio import activity

from common.blob_store import BlobCorrupt, BlobNotFound, BlobStore
from common.errors import NonRetryableError, TemplateVersionUnavailable
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
from harness_activity.runner import HarnessRunner, RunResult, StopRun, Superseded, Usage
from registry.loader import Registry

log = logging.getLogger("praxis.harness")
CONTINUE_MESSAGE = "Continue the task from where it stopped."
DEFAULT_HEARTBEAT_TIMEOUT = timedelta(seconds=30)
# Real attempts per turn (worker lost, timeout, storage unavailable). Template
# version refusals do not count; the Workflow's schedule_to_close bounds those.
MAX_REAL_ATTEMPTS = 5


class AttemptsExhausted(NonRetryableError):
    """The turn was lost or failed MAX_REAL_ATTEMPTS times."""


class HarnessInputError(NonRetryableError):
    """A failure retrying cannot fix: a corrupt or missing snapshot, a request the
    model server rejects (for example, context too long), a missing task row."""


@dataclass
class Progress:
    """Cumulative over the attempts of one turn (RFC: lost attempts count)."""

    tokens_in: int = 0
    tokens_out: int = 0
    tool_calls: int = 0
    inner_turns: int = 0
    checkpoint_id: str | None = None
    refusals: int = 0

    @classmethod
    def from_details(cls, details: Any) -> Progress:
        """Tolerant of older or newer heartbeat layouts (review F17)."""
        known = {f.name for f in dataclasses.fields(cls)}
        if not isinstance(details, dict):
            return cls()
        return cls(**{k: v for k, v in details.items() if k in known})

    def plus(self, usage: Usage) -> Progress:
        return dataclasses.replace(
            self,
            tokens_in=self.tokens_in + usage.tokens_in,
            tokens_out=self.tokens_out + usage.tokens_out,
            tool_calls=self.tool_calls + usage.tool_calls,
            inner_turns=self.inner_turns + usage.inner_turns,
        )


def worker_identity(template: str) -> str:
    return f"{socket.gethostname()}@{os.getpid()}/{template}"


class _Heartbeat:
    """Heartbeats every `heartbeat_timeout / 3` with the live, cumulative usage."""

    def __init__(self, base: Progress) -> None:
        self.base = base
        self.usage = Usage()
        self.checkpoint_id: str | None = base.checkpoint_id

    def current(self) -> Progress:
        progress = self.base.plus(self.usage)
        progress.checkpoint_id = self.checkpoint_id
        return progress

    @contextlib.asynccontextmanager
    async def running(self) -> AsyncIterator[None]:
        task = asyncio.create_task(self._loop())
        try:
            yield
        finally:
            activity.heartbeat(asdict(self.current()))
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _loop(self) -> None:
        timeout = activity.info().heartbeat_timeout or DEFAULT_HEARTBEAT_TIMEOUT
        interval = max(0.5, timeout.total_seconds() / 3)
        while True:
            activity.heartbeat(asdict(self.current()))
            await asyncio.sleep(interval)


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
        info = activity.info()
        prior = Progress.from_details(info.heartbeat_details[0] if info.heartbeat_details else {})
        loaded = self.registry.templates.get(turn.template)
        if loaded is None or loaded.hash != turn.template_hash:
            # Retryable, and not counted as an attempt: the next attempt reads the
            # refusal count from this heartbeat (review F7).
            prior.refusals += 1
            activity.heartbeat(asdict(prior))
            raise TemplateVersionUnavailable(
                f"this worker runs {loaded.template.ref if loaded else 'no'} "
                f"{turn.template}, not version {turn.template_version} of the task"
            )
        attempt = info.attempt
        real_attempt = attempt - prior.refusals
        if real_attempt > MAX_REAL_ATTEMPTS:
            await self.attempts.close_unfinished(turn.task_id, turn.turn, "attempts_exhausted")
            raise AttemptsExhausted(f"turn {turn.turn} was lost {MAX_REAL_ATTEMPTS} times")
        with log_context(
            task_id=turn.task_id,
            workflow_id=info.workflow_id,
            turn=turn.turn,
            attempt=attempt,
            worker=self.identity,
        ):
            heartbeat = _Heartbeat(prior)
            workdir = self.scratch / turn.task_id / f"{turn.turn}-{attempt}-{uuid.uuid4().hex[:8]}"
            try:
                async with heartbeat.running():
                    await self.attempts.start(turn.task_id, turn.turn, attempt, self.identity)
                    return await self._run(turn, attempt, real_attempt, heartbeat, workdir)
            except (BlobCorrupt, BlobNotFound) as e:
                await self.attempts.close_unfinished(turn.task_id, turn.turn, "input_unreadable")
                raise HarnessInputError(f"checkpoint or input unreadable: {e}") from e
            except BadRequestError as e:
                await self.attempts.close_unfinished(turn.task_id, turn.turn, "model_rejected")
                raise HarnessInputError(f"the model server rejected the request: {e}") from e
            finally:
                shutil.rmtree(workdir, ignore_errors=True)

    async def _run(
        self,
        turn: TurnInput,
        attempt: int,
        real_attempt: int,
        heartbeat: _Heartbeat,
        workdir: Path,
    ) -> TurnOutcome:
        loaded = self.registry.templates[turn.template]
        template_ref = loaded.template.ref
        config = build_config(self.registry, loaded, turn.task_id)
        session = SQLAlchemySession(turn.task_id, engine=self.engine)
        seq = 0

        latest = await self.checkpoints.latest(turn.task_id)
        if latest is not None:
            data = await self.blobs.get(latest.workspace_ref)
            await asyncio.to_thread(ws.unpack, data, workdir)
            items = await session.get_items()
            if len(items) < latest.session_position:
                log.warning(
                    "session shorter than its checkpoint",
                    extra={"fields": {"items": len(items), "position": latest.session_position}},
                )
            for _ in range(len(items) - latest.session_position):
                await session.pop_item()
            heartbeat.checkpoint_id = latest.checkpoint_id
            if latest.finish is not None:  # lost after finish_task: go straight to finish
                result = RunResult(
                    latest.finish["status"],
                    Usage(),
                    summary=latest.finish.get("summary", ""),
                    questions=latest.finish.get("questions", []),
                )
                return await self._finish(
                    turn, attempt, real_attempt, heartbeat, workdir, result, template_ref
                )
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
            heartbeat.checkpoint_id = cp_id
            CHECKPOINT_BYTES.observe(len(data))
            CHECKPOINT_SECONDS.observe(time.monotonic() - started)

        async def before_model_call(usage: Usage) -> None:
            if await self.attempts.newer_attempt_exists(turn.task_id, turn.turn, attempt):
                raise Superseded("a newer attempt of this turn is running")
            await checkpoint()
            used = heartbeat.current()  # lost attempts included (review F1)
            if used.tokens_in + used.tokens_out >= turn.remaining_tokens:
                raise StopRun("token budget for the task is used up")

        try:
            result = await self.runner.run(
                config, workdir, session, input_text, before_model_call, heartbeat.usage
            )
        except Superseded:
            # A newer attempt owns the turn: write no checkpoint and no attempt
            # outcome; Temporal discards this attempt's result (review F4).
            log.warning("attempt superseded; stopping without writing")
            raise
        usage = result.usage
        TOKENS.labels(template=template_ref, direction="in").inc(usage.tokens_in)
        TOKENS.labels(template=template_ref, direction="out").inc(usage.tokens_out)
        TOOL_CALLS.labels(template=template_ref, tool="any").inc(usage.tool_calls)
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
        return await self._finish(
            turn, attempt, real_attempt, heartbeat, workdir, result, template_ref
        )

    async def _fresh_start(self, task_id: str, workdir: Path) -> str:
        row = await self.tasks.get(task_id)
        if row is None:
            raise HarnessInputError(f"task {task_id} is not recorded")
        workdir.mkdir(parents=True, exist_ok=True)
        for name, ref_json in (row["input_refs"] or {}).items():
            data = await self.blobs.get(BlobRef.model_validate(ref_json))
            (workdir / name).write_bytes(data)
        return (await self.blobs.get(BlobRef.model_validate(row["instructions_ref"]))).decode()

    async def _finish(
        self,
        turn: TurnInput,
        attempt: int,
        real_attempt: int,
        heartbeat: _Heartbeat,
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
        progress = heartbeat.current()
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
            attempts=real_attempt,
            summary=result.summary[:2000],
            questions=result.questions or [],
            outputs=outputs,
            error=result.error,
        )
