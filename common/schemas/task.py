"""Task schemas: the request, the Workflow's inputs and outputs, and attempts (plan §5)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from common.schemas.base import Slug, Strict
from common.schemas.blob import BlobRef

TASK_ID_PATTERN = r"^task-[a-z0-9-]{8,64}$"
SUMMARY_MAX = 2000


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"must be a relative path inside the workspace: {value!r}")
    return value


WorkspacePath = Annotated[str, AfterValidator(_relative_path)]


class Artifact(Strict):
    """An output file of a task: its workspace path and stored bytes."""

    schema_version: Literal[1] = 1
    path: WorkspacePath
    ref: BlobRef


class TaskRequest(Strict):
    """What a client may ask for. Capabilities are not part of it (plan §4.10)."""

    schema_version: Literal[1] = 1
    task_id: str | None = Field(default=None, pattern=TASK_ID_PATTERN)
    profile: Annotated[str, Slug]
    template: Annotated[str, Slug] | None = None
    instructions: str = Field(min_length=1, max_length=100_000)
    input_files: list[str] = []
    outputs: list[WorkspacePath] = []
    # Put the task in an existing request instead of a new one, so it may message the
    # request's other tasks (Phase 2 messaging D5); the CLI checks it exists.
    join_request: str | None = Field(default=None, pattern=r"^req-[A-Za-z0-9-]{1,80}$")


class TaskStart(Strict):
    """`TaskWorkflow`'s input: IDs and blob references only (plan §2 small histories)."""

    schema_version: Literal[1] = 1
    task_id: str = Field(pattern=TASK_ID_PATTERN)
    request_id: str
    profile: str
    template: str
    instructions_ref: BlobRef
    input_refs: dict[WorkspacePath, BlobRef] = {}
    outputs: list[WorkspacePath] = []


class TurnInput(Strict):
    schema_version: Literal[1] = 1
    task_id: str = Field(pattern=TASK_ID_PATTERN)
    turn: int = Field(ge=1)
    template: str
    template_version: int = Field(ge=1)
    template_hash: str
    remaining_tokens: int = Field(ge=0)
    remaining_wall_time: timedelta
    request_id: str = ""
    # Passed to comms_mcp, which caps an ask's deadline with it (Phase 2 messaging D14).
    max_ask_wait: timedelta = timedelta(minutes=10)


class TurnOutcome(Strict):
    schema_version: Literal[1] = 1
    status: Literal["done", "continue", "needs_input", "waiting"]
    checkpoint_id: str | None = None
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    inner_turns: int = Field(default=0, ge=0)
    attempts: int = Field(default=1, ge=1)
    summary: str = Field(default="", max_length=SUMMARY_MAX)
    questions: list[str] = []
    outputs: list[Artifact] = []
    error: str | None = None
    # False when some usage could not be observed (DSH migration plan D7, D9).
    usage_known: bool = True


class TaskResult(Strict):
    schema_version: Literal[1] = 1
    task_id: str
    status: Literal["succeeded", "failed", "needs_input"]
    summary: str = Field(default="", max_length=SUMMARY_MAX)
    artifacts: list[Artifact] = []
    questions: list[str] = []
    failure_reason: str | None = None
    tier_used: str
    template: str
    template_version: int
    template_hash: str
    turns: int = Field(ge=0)
    attempts: int = Field(ge=0)
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    inner_turns: int = Field(default=0, ge=0)
    usage_known: bool = True


AttemptOutcome = Literal[
    "started",
    "done",
    "continue",
    "needs_input",
    "waiting",
    "failed",
    "lost",
    "refused",
    "cancelled",
]


class ExecutionAttempt(Strict):
    """One `task_attempts` row."""

    schema_version: Literal[1] = 1
    task_id: str
    turn: int = Field(ge=1)
    attempt: int = Field(ge=1)
    worker_identity: str
    outcome: AttemptOutcome
    failure_category: str | None = None
    # The turn's cumulative usage through this attempt. None when a request of this
    # attempt (or, for a lost attempt, of one up to it) was never observed; numbers
    # with usage_known false include the conservative D9 charge (D7, review F69).
    tokens_in: int | None = 0
    tokens_out: int | None = 0
    usage_known: bool = True
    tool_calls: int = 0
    started_at: datetime
    ended_at: datetime | None = None


class ResolvedTask(Strict):
    """The template and effective budget for a task, fixed when it starts."""

    schema_version: Literal[1] = 1
    template: str
    template_version: int
    template_hash: str
    task_queue: str
    tier: str
    max_turns: int = Field(ge=1)
    max_tokens: int = Field(ge=1)
    max_wall_time: timedelta
    turn_timeout: timedelta
    heartbeat_timeout: timedelta
    # Phase 2 messaging D14; defaults keep payloads recorded before them decoding.
    idle_timeout: timedelta = timedelta(minutes=10)
    max_ask_wait: timedelta = timedelta(minutes=10)
    max_wakes: int = Field(default=50, ge=1)


class RecordTaskInput(Strict):
    schema_version: Literal[1] = 1
    start: TaskStart
    resolved: ResolvedTask


class CompleteTaskInput(Strict):
    schema_version: Literal[1] = 1
    task_id: str
    status: Literal["succeeded", "failed", "needs_input"]
    summary: str = Field(default="", max_length=SUMMARY_MAX)
    artifacts: list[Artifact] = []
    questions: list[str] = []
    failure_reason: str | None = None
    resolved: ResolvedTask
    turns: int = Field(ge=0)
    attempts: int = Field(ge=0)
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    inner_turns: int = Field(default=0, ge=0)
    usage_known: bool = True
