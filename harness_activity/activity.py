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

A runner that keeps its attempts outside the worker process (DSH) supplies the
attempt's workspace and session store through `open_attempt`; the Activity
closes that scope after its last write. For such a runner the Activity also
charges the model requests earlier attempts dispatched but never saw answered
(DSH migration plan D9), and records a failure the runner classified.
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
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from openai import BadRequestError
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio import activity
from temporalio.exceptions import ApplicationError

from common.blob_store import BlobCorrupt, BlobNotFound, BlobStore
from common.errors import NonRetryableError, TemplateVersionUnavailable
from common.events import EventTransport, Writer
from common.observability import log_context
from common.observability.metrics import (
    ACTIVITY_SECONDS,
    CHECKPOINT_BYTES,
    CHECKPOINT_SECONDS,
    HEARTBEAT_LAG_SECONDS,
    TOKENS,
)
from common.persistence.fence import FenceRejected
from common.persistence.messages import Delivered, MessageRepository, Sender
from common.persistence.repositories import (
    AttemptRepository,
    Checkpoint,
    CheckpointRepository,
    TaskRepository,
    UsageLedgerRepository,
)
from common.schemas import Artifact, BlobRef, TurnInput, TurnOutcome
from harness_activity import workspace as ws
from harness_activity.config import build_config
from harness_activity.dsh.composition import DEFAULT_CONTEXT_WINDOW
from harness_activity.dsh.ledger import unknown_charge
from harness_activity.events import AttemptEvents, BatchingPublisher, NoOpSink
from harness_activity.runner import (
    AttemptContext,
    AttemptScope,
    HarnessRunner,
    RunnerFailure,
    RunResult,
    StopRun,
    Superseded,
    Unserviceable,
    Usage,
    WorkerUnserviceable,
)
from harness_activity.session_store import SessionStore, SQLAlchemySessionStore
from harness_activity.tools import WorkspaceError, read_regular
from registry.loader import Registry

log = logging.getLogger("praxis.harness")
CONTINUE_MESSAGE = "Continue the task from where it stopped."
DEFAULT_HEARTBEAT_TIMEOUT = timedelta(seconds=30)
# Real attempts per turn (worker lost, timeout, storage unavailable). Template
# version refusals do not count; the Workflow's schedule_to_close bounds those.
MAX_REAL_ATTEMPTS = 5
# A runner with a deadline must have stopped its attempt this long before the
# Activity's own timeout: the 5 s stop grace (R8) and the writes that follow.
STOP_MARGIN_SECONDS = 20.0


class AttemptsExhausted(NonRetryableError):
    """The turn was lost or failed MAX_REAL_ATTEMPTS times."""


class EventsUnavailable(Exception):
    """Retryable: the attempt's events could not be stored, so its finish is not
    written either (they share the app database; Phase 2 events plan R8)."""


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
    # The real attempt that sent this heartbeat, so a turn ended by
    # schedule_to_close still reports its attempts (follow-up M1).
    attempts: int = 0
    # Requests whose usage was never observed and whose conservative charge is
    # already in the totals above (DSH migration plan D9); the totals are then
    # not exact, so `usage_known` is false (D7).
    unknown_requests: int = 0
    usage_known: bool = True

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
        last = time.monotonic()
        while True:
            activity.heartbeat(asdict(self.current()))
            now = time.monotonic()
            HEARTBEAT_LAG_SECONDS.labels(activity="run_harness_turn").observe(now - last)
            last = now
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
        session_store: Callable[[str, AsyncEngine], SessionStore] = SQLAlchemySessionStore,
        open_attempt: Callable[[AttemptContext], Awaitable[AttemptScope]] | None = None,
        preflight: Callable[[], Awaitable[None]] | None = None,
        events: EventTransport | None = None,
    ) -> None:
        self.registry = registry
        self.engine = engine
        self.blobs = blobs
        self.runner = runner
        self.scratch = scratch
        self.identity = identity
        self.session_store = session_store
        self.open_attempt = open_attempt
        # Checked before an attempt is recorded; raises `Unserviceable` (F99).
        self.preflight = preflight
        # Where attempts publish their events; None publishes nothing (unit tests).
        self.events = events
        # Told when this worker must stop polling its queue.
        self.on_unserviceable: Callable[[str], None] | None = None
        self.ledger = UsageLedgerRepository(engine)
        self.tasks = TaskRepository(engine)
        self.attempts = AttemptRepository(engine)
        self.checkpoints = CheckpointRepository(engine)

    @activity.defn(name="run_harness_turn")
    async def run_harness_turn(self, turn: TurnInput) -> TurnOutcome:
        info = activity.info()
        prior = Progress.from_details(info.heartbeat_details[0] if info.heartbeat_details else {})
        loaded = self.registry.templates.get(turn.template)
        if loaded is None or loaded.hash != turn.template_hash:
            # Not a real attempt, but newer than the ones before it (D10, review F27);
            # the row first, so a refusal the next attempt subtracts exists (F149).
            await self.attempts.record_refusal(turn.task_id, turn.turn, info.attempt, self.identity)
            # Retryable, and not counted as an attempt: the next attempt reads the
            # refusal count from this heartbeat (review F7).
            prior.refusals += 1
            activity.heartbeat(asdict(prior))
            raise TemplateVersionUnavailable(
                f"this worker runs {loaded.template.ref if loaded else 'no'} "
                f"{turn.template}, not version {turn.template_version} of the task"
            )
        if self.preflight is not None:
            try:
                await self.preflight()
            except Unserviceable as e:
                # Like a version refusal: not an attempt, and this worker stops
                # polling, so a worker that can serve takes the turn (R17, F99).
                # The row first: a refusal the next attempt subtracts must exist (F147).
                await self.attempts.record_refusal(
                    turn.task_id, turn.turn, info.attempt, self.identity, "dsh_unserviceable"
                )
                prior.refusals += 1
                activity.heartbeat(asdict(prior))
                log.error("worker cannot serve its queue", extra={"fields": {"error": str(e)}})
                if self.on_unserviceable is not None:
                    self.on_unserviceable(str(e))
                raise WorkerUnserviceable(str(e)) from e
        attempt = info.attempt
        real_attempt = attempt - prior.refusals
        began = time.monotonic()
        outcome = "error"
        prior.attempts = real_attempt
        heartbeat = _Heartbeat(prior)
        with log_context(
            request_id=turn.request_id,
            task_id=turn.task_id,
            workflow_id=info.workflow_id,
            turn=turn.turn,
            attempt=attempt,
            worker=self.identity,
        ):
            try:
                if real_attempt > MAX_REAL_ATTEMPTS:
                    raise AttemptsExhausted(f"turn {turn.turn} was lost {MAX_REAL_ATTEMPTS} times")
                result = await self._attempt(turn, attempt, real_attempt, heartbeat)
                outcome = result.status
                return result
            except RunnerFailure as e:
                await self._runner_failed(turn, attempt, real_attempt, heartbeat, e)
                raise  # unreachable: _runner_failed always raises
            except NonRetryableError as e:
                # The turn has failed for good: close its open attempt rows and tell
                # the Workflow what the turn used, lost attempts included (gate F1, F2).
                exhausted = isinstance(e, AttemptsExhausted)
                await self.attempts.close_unfinished(
                    turn.task_id,
                    turn.turn,
                    "lost_or_timed_out" if exhausted else type(e).__name__,
                    outcome="lost" if exhausted else "failed",
                    through_attempt=attempt,
                )
                if self.open_attempt is not None:
                    # No later attempt will charge what this turn left unobserved (F59).
                    await self._charge(turn, attempt + 1, heartbeat)
                used = heartbeat.current()
                details = {**asdict(used), "attempts": min(real_attempt, MAX_REAL_ATTEMPTS)}
                log.error("harness turn failed for good", extra={"fields": {"error": str(e)}})
                raise ApplicationError(
                    str(e), details, type=type(e).__name__, non_retryable=True
                ) from e
            finally:
                ACTIVITY_SECONDS.labels(activity="run_harness_turn", outcome=outcome).observe(
                    time.monotonic() - began
                )

    async def _runner_failed(
        self,
        turn: TurnInput,
        attempt: int,
        real_attempt: int,
        heartbeat: _Heartbeat,
        failure: RunnerFailure,
    ) -> None:
        """Record an attempt its runner classified as failed, then raise for Temporal:
        retryable or not as classified, or the cancellation that stopped it.

        Requests this attempt dispatched but never saw answered are charged now (D9,
        review F59): a cancel or a non-retryable failure has no later attempt to do
        it, and the turn's usage is then not known. The attempt's own row stores
        NULL tokens for them, never 0 (R12)."""
        own_unknown = 0
        if self.open_attempt is not None:
            await self._charge(turn, attempt + 1, heartbeat)
            own_unknown = await self.ledger.unknown_requests(turn.task_id, turn.turn, attempt)
        used = heartbeat.current()
        cancelled = failure.cancelled and failure.category == "DshCancelled"
        with contextlib.suppress(FenceRejected):  # a stale attempt writes nothing (R6)
            await self.attempts.finish(
                turn.task_id,
                turn.turn,
                attempt,
                outcome="cancelled" if cancelled else "failed",  # a forced stop failed (R9)
                tokens_in=None if own_unknown else used.tokens_in,
                tokens_out=None if own_unknown else used.tokens_out,
                tool_calls=used.tool_calls,
                failure_category=failure.category,
                fenced=True,
                usage_known=used.usage_known,
            )
        log.warning(
            "harness attempt failed",
            extra={"fields": {"category": failure.category, "retryable": failure.retryable}},
        )
        if failure.cancelled:
            raise asyncio.CancelledError() from failure
        if not failure.retryable:
            await self.attempts.close_unfinished(
                turn.task_id,
                turn.turn,
                failure.category,
                outcome="failed",
                through_attempt=attempt,
            )
        details = {**asdict(used), "attempts": min(real_attempt, MAX_REAL_ATTEMPTS)}
        raise ApplicationError(
            failure.category, details, type=failure.category, non_retryable=not failure.retryable
        ) from failure

    async def _charge(self, turn: TurnInput, below: int, heartbeat: _Heartbeat) -> None:
        """Make the heartbeat's usage at least what the gateway ledger holds for the
        attempts of this turn below `below`: settled usage, plus the D9 charge for
        every request whose usage was never observed, which makes it not known.

        R11, D9: usage comes from the ledger, so a request settled between the last
        heartbeat and a worker crash is never lost. The ledger is derived afresh each
        time, so charging it again never counts a request twice."""
        unknown, settled_in, settled_out, settled_count = await self.ledger.close_unknown(
            turn.task_id, turn.turn, below
        )
        if not (unknown or settled_in or settled_out or settled_count):
            return
        template = self.registry.templates[turn.template].template
        window = template.context_window or DEFAULT_CONTEXT_WINDOW
        charge_in, charge_out = unknown_charge(unknown, window)
        base, live = heartbeat.base, heartbeat.usage
        heartbeat.base = dataclasses.replace(
            base,
            tokens_in=max(base.tokens_in, settled_in + charge_in - live.tokens_in),
            tokens_out=max(base.tokens_out, settled_out + charge_out - live.tokens_out),
            inner_turns=max(base.inner_turns, settled_count + unknown - live.inner_turns),
            unknown_requests=max(unknown, base.unknown_requests),
            usage_known=base.usage_known and unknown == 0,
        )

    async def _open(self, turn: TurnInput, attempt: int, heartbeat: _Heartbeat) -> AttemptScope:
        """Charge what earlier attempts of this turn left unobserved (D9), then let
        the runner open the attempt."""
        assert self.open_attempt is not None
        info = activity.info()
        await self._charge(turn, attempt, heartbeat)
        used = heartbeat.current()
        timeout = info.start_to_close_timeout or turn.remaining_wall_time
        seconds = min(timeout, turn.remaining_wall_time).total_seconds()
        return await self.open_attempt(
            AttemptContext(
                task_id=turn.task_id,
                turn=turn.turn,
                attempt=attempt,
                workflow_id=info.workflow_id or "",
                remaining_tokens=turn.remaining_tokens - used.tokens_in - used.tokens_out,
                deadline=time.monotonic() + max(1.0, seconds - STOP_MARGIN_SECONDS),
            )
        )

    async def _attempt(
        self, turn: TurnInput, attempt: int, real_attempt: int, heartbeat: _Heartbeat
    ) -> TurnOutcome:
        workdir = self.scratch / turn.task_id / f"{turn.turn}-{attempt}-{uuid.uuid4().hex[:8]}"
        scope: AttemptScope | None = None
        workflow_id = activity.info().workflow_id or turn.task_id
        try:
            async with heartbeat.running():
                try:
                    await self.attempts.start(turn.task_id, turn.turn, attempt, self.identity)
                except FenceRejected as e:  # started late: a newer attempt owns the turn
                    raise Superseded(str(e)) from e
                # The attempt's one event stream (Phase 2 events plan D2).
                publisher = (
                    BatchingPublisher(
                        self.events,
                        Writer(turn.task_id, turn.turn, attempt),
                        workflow_id,
                        f"{turn.task_id}:{turn.turn}:{attempt}",
                    )
                    if self.events is not None
                    else None
                )
                events = AttemptEvents(
                    publisher or NoOpSink(), workflow_id, turn.task_id, turn.turn, attempt
                )
                try:
                    # The attempt's first event, before anything else can fail (R9).
                    latest = await self.checkpoints.latest(turn.task_id)
                    events.emit("reset", restored_from=latest.checkpoint_id if latest else None)
                    if self.open_attempt is not None:
                        scope = await self._open(turn, attempt, heartbeat)
                        workdir = scope.workspace
                    return await self._run(
                        turn,
                        attempt,
                        real_attempt,
                        heartbeat,
                        workdir,
                        events,
                        publisher,
                        latest,
                        scope.store if scope else None,
                    )
                except BaseException as e:
                    # Every other ending stores its events too; the original error
                    # still propagates (R8; ADR-0007).
                    if publisher is not None and not publisher.closed:
                        if events.seq == 0:  # failed before the reset: still open with one
                            events.emit("reset", restored_from=None)
                        if not isinstance(e, Superseded):
                            events.emit("status", **_failure_status(e))
                        problem = await publisher.close()
                        if problem is not None:
                            log.warning(
                                "attempt events not stored",
                                extra={"fields": {"error": repr(problem)}},
                            )
                    raise
        except (BlobCorrupt, BlobNotFound) as e:
            raise HarnessInputError(f"checkpoint or input unreadable: {e}") from e
        except BadRequestError as e:
            raise HarnessInputError(f"the model server rejected the request: {e}") from e
        finally:
            if scope is not None:
                # Ends the attempt's processes and removes its tree, whatever happened.
                with contextlib.suppress(Exception):
                    await asyncio.shield(scope.close())
            shutil.rmtree(workdir, ignore_errors=True)

    async def _run(
        self,
        turn: TurnInput,
        attempt: int,
        real_attempt: int,
        heartbeat: _Heartbeat,
        workdir: Path,
        events: AttemptEvents,
        publisher: BatchingPublisher | None,
        latest: Checkpoint | None,
        attempt_store: SessionStore | None = None,
    ) -> TurnOutcome:
        loaded = self.registry.templates[turn.template]
        template_ref = loaded.template.ref
        config = build_config(
            self.registry,
            loaded,
            turn.task_id,
            turn=turn.turn,
            attempt=attempt,
            max_ask_wait=turn.max_ask_wait,
        )
        config = dataclasses.replace(config, finish_check=self._finish_check(turn, attempt))
        store = attempt_store or self.session_store(turn.task_id, self.engine)
        session = store.session
        seq = 0

        if latest is not None:
            data = await self.blobs.get(latest.workspace_ref)
            await asyncio.to_thread(ws.unpack, data, workdir)
            await store.load(latest)
            heartbeat.checkpoint_id = latest.checkpoint_id
            # Lost after finish_task in this turn: go straight to finish. A finish of
            # an earlier turn (a `waiting` one) starts a new turn (Phase 2 messaging).
            if latest.finish is not None and latest.turn == turn.turn:
                result = RunResult(
                    latest.finish["status"],
                    Usage(),
                    summary=latest.finish.get("summary", ""),
                    questions=latest.finish.get("questions", []),
                )
                return await self._finish(
                    turn,
                    attempt,
                    real_attempt,
                    heartbeat,
                    workdir,
                    result,
                    template_ref,
                    events,
                    publisher,
                )
            input_text = CONTINUE_MESSAGE
            if latest.turn < turn.turn:  # a new turn; a rerun of this one already has them
                woken = await self._woken_input(turn, attempt)
                input_text = woken or input_text
        else:
            await store.load(None)
            input_text = await self._fresh_start(turn.task_id, workdir)

        async def checkpoint(finish: dict[str, Any] | None = None) -> None:
            nonlocal seq
            started = time.monotonic()
            data = await asyncio.to_thread(ws.pack, workdir)
            ref = await self.blobs.put(data, content_type="application/gzip", retention="task")
            snapshot = await store.capture()
            position = snapshot.position
            cp_id = f"{turn.task_id}:{turn.turn}:{attempt}:{seq}"
            try:
                await self.checkpoints.insert_fenced(
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
                        session_ref=snapshot.session_ref,
                        session_digest=snapshot.session_digest,
                    )
                )
            except FenceRejected as e:
                raise Superseded(str(e)) from e
            seq += 1
            heartbeat.checkpoint_id = cp_id
            CHECKPOINT_BYTES.observe(len(data))
            CHECKPOINT_SECONDS.observe(time.monotonic() - started)

        async def before_model_call(usage: Usage) -> None:
            # Cheap early exit; the fenced checkpoint insert is the authoritative check.
            if await self.attempts.newer_attempt_exists(turn.task_id, turn.turn, attempt):
                raise Superseded("a newer attempt of this turn is running")
            await checkpoint()
            used = heartbeat.current()  # lost attempts included (review F1)
            if used.tokens_in + used.tokens_out >= turn.remaining_tokens:
                raise StopRun("token budget for the task is used up")

        try:
            result = await self.runner.run(
                config, workdir, session, input_text, before_model_call, heartbeat.usage, events
            )
        except Superseded:
            # A newer attempt owns the turn: write no checkpoint and no attempt
            # outcome; Temporal discards this attempt's result (review F4).
            log.warning("attempt superseded; stopping without writing")
            raise
        if result.status in ("done", "needs_input") and config.finish_check is not None:
            # R19 again, now that every tool of the last step has returned: an
            # ask_agent run in parallel with finish_task may have committed after
            # finish_task's own check. The next turn's finish is then refused.
            try:
                blocking = await MessageRepository(self.engine).blocking_finish(
                    Sender(turn.task_id, turn.turn, attempt)
                )
            except FenceRejected as e:  # a newer attempt owns the turn (review F5)
                raise Superseded(str(e)) from e
            if blocking:
                result = dataclasses.replace(
                    result,
                    status="continue",
                    summary="finish_task alongside " + "; ".join(blocking),
                    questions=None,
                )
        usage = result.usage
        TOKENS.labels(template=template_ref, direction="in").inc(usage.tokens_in)
        TOKENS.labels(template=template_ref, direction="out").inc(usage.tokens_out)
        finish = (
            {
                "status": result.status,
                "summary": result.summary,
                "questions": result.questions or [],
            }
            if result.status in ("done", "needs_input", "waiting")  # D18
            else None
        )
        return await self._finish(
            turn,
            attempt,
            real_attempt,
            heartbeat,
            workdir,
            result,
            template_ref,
            events,
            publisher,
            finish_checkpoint=lambda: checkpoint(finish),
        )

    async def _woken_input(self, turn: TurnInput, attempt: int) -> str | None:
        """The input of a woken turn: the rows its claim assigned to it, read once
        (a fenced write), or None when the turn was not started by a claim."""
        delivered = await MessageRepository(self.engine).read_claimed(
            Sender(turn.task_id, turn.turn, attempt)
        )
        return render_inbox(turn.task_id, delivered) if delivered else None

    def _finish_check(self, turn: TurnInput, attempt: int) -> Callable[[], list[str]]:
        """The open-question check `finish_task` runs from a tool thread (Phase 2
        messaging R19, D8): it runs on this Activity's event loop."""
        loop = asyncio.get_running_loop()
        messages = MessageRepository(self.engine)
        sender = Sender(turn.task_id, turn.turn, attempt)

        def check() -> list[str]:
            future = asyncio.run_coroutine_threadsafe(messages.blocking_finish(sender), loop)
            return future.result(timeout=30)

        return check

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
        events: AttemptEvents,
        publisher: BatchingPublisher | None,
        finish_checkpoint: Callable[[], Awaitable[None]] | None = None,
    ) -> TurnOutcome:
        """Every success path ends here. The attempt's events are flushed first: a
        refused flush makes no finish write (R5), and a flush that fails for good
        writes none either (R8). Then the finish checkpoint, artifacts and outcome."""
        events.emit("status", status=result.status)
        if publisher is not None:
            problem = await publisher.close()
            if isinstance(problem, FenceRejected):
                raise Superseded(str(problem)) from problem
            if problem is not None:
                raise EventsUnavailable(f"attempt events not stored: {problem!r}") from problem
        if finish_checkpoint is not None:
            await finish_checkpoint()
        outputs: list[Artifact] = []
        if result.status in ("done", "waiting"):  # a waiting turn keeps its outputs (D18)
            try:  # a stale attempt publishes no artifact (D10, R7)
                await self.attempts.assert_current(turn.task_id, turn.turn, attempt)
            except FenceRejected as e:
                raise Superseded(str(e)) from e
            row = await self.tasks.get(turn.task_id)
            for path in (row or {}).get("outputs") or []:
                try:  # a regular file in the workspace, never through a link (F97)
                    data = read_regular(workdir, path)
                except (WorkspaceError, OSError):
                    continue
                ref = await self.blobs.put(data, retention="audit")
                outputs.append(Artifact(path=path, ref=ref))
        progress = heartbeat.current()
        try:
            await self.attempts.finish(
                turn.task_id,
                turn.turn,
                attempt,
                outcome=result.status,
                tokens_in=progress.tokens_in,
                tokens_out=progress.tokens_out,
                tool_calls=progress.tool_calls,
                failure_category="model_behavior" if result.error else None,
                fenced=True,
                usage_known=progress.usage_known,
            )
        except FenceRejected as e:
            raise Superseded(str(e)) from e
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
            usage_known=progress.usage_known,
        )


def _failure_status(error: BaseException) -> dict[str, str]:
    """The `status` event of an attempt that did not finish: no message text."""
    if isinstance(error, asyncio.CancelledError):
        return {"status": "cancelled", "error": "CancelledError"}
    if isinstance(error, RunnerFailure):
        return {"status": "cancelled" if error.cancelled else "failed", "error": error.category}
    return {"status": "failed", "error": type(error).__name__}


def render_inbox(task_id: str, delivered: list[Delivered]) -> str:
    """The woken turn's input (Phase 2 messaging D7): each message, question, reply
    and closed question, with the IDs the agent needs to answer."""
    lines = ["You were woken because these arrived since your last turn:"]
    for d in delivered:
        if d.sender_task == task_id and d.kind == "ask":  # one of its own questions
            why = (
                "no answer came by the deadline"
                if d.status == "expired"
                else ("it was cancelled: the other task ended without replying")
            )
            lines.append(f"- Your question {d.correlation_id} to {d.recipient_task}: {why}.")
        elif d.kind == "ask":
            lines.append(
                f"- Question {d.correlation_id} from {d.sender_task} (answer it with "
                f'send_to_agent, reply_to="{d.correlation_id}"): {d.body}'
            )
        elif d.kind == "reply":
            lines.append(f"- Reply from {d.sender_task} to your question {d.reply_to}: {d.body}")
        else:
            lines.append(f"- Message from {d.sender_task}: {d.body}")
    lines.append(
        "Continue the task. When you are done call finish_task, or call it with status "
        '"waiting" if you expect more messages.'
    )
    return "\n".join(lines)
