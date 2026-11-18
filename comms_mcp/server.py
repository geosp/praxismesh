"""The comms MCP server: messaging between tasks of one request (Phase 2
messaging D8, D9, D13, D15), run as a stdio subprocess per harness attempt.

Tools: `send_to_agent` (a message, or with `reply_to` a reply), `ask_agent` (a
question with a deadline), `post_status` (a stage and progress, published as an
event by the runner) and `get_task_context` (the request's tasks).

Identity comes only from the worker (D9): `PRAXIS_TASK_ID`, `PRAXIS_TURN` and
`PRAXIS_ATTEMPT`; no tool takes a sender. Every write is fenced (R27) and keyed by
the turn, tool and arguments, so a retried attempt repeating a call stores nothing
new (R13). It connects as `praxis_comms` through `PRAXIS_COMMS_DB_URL` (D13); an
ask's deadline is capped at `PRAXIS_MAX_ASK_WAIT` seconds (D8, D14).
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from common.persistence.fence import FenceRejected
from common.persistence.messages import MessageRepository, Sender, SendResult, idempotency_key

DEFAULT_WAIT_S = 300
WAIT_INSTRUCTION = (
    'Now call finish_task with status "waiting": you are woken when the answer arrives or '
    "the deadline passes."
)
Stage = Literal["planning", "working", "waiting", "reviewing", "done"]

server = MCPServer(name="comms")
_engine: AsyncEngine | None = None


def engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = os.environ.get("PRAXIS_COMMS_DB_URL", "")
        if not url:
            raise RuntimeError("PRAXIS_COMMS_DB_URL is not set for the comms MCP server")
        _engine = create_async_engine(url)
    return _engine


def me() -> Sender:
    try:
        return Sender(
            os.environ["PRAXIS_TASK_ID"],
            int(os.environ["PRAXIS_TURN"]),
            int(os.environ["PRAXIS_ATTEMPT"]),
        )
    except (KeyError, ValueError) as e:
        raise RuntimeError("the worker did not give this server its task, turn and attempt") from e


def _key(sender: Sender, tool: str, arguments: dict[str, Any]) -> str:
    return idempotency_key(sender.task_id, sender.turn, tool, arguments)


def _result(result: SendResult) -> dict[str, Any]:
    if not result.ok:
        raise ToolError(f"refused: {result.reason}")
    out: dict[str, Any] = {"message_id": result.message_id}
    if result.correlation_id is not None:
        out["correlation_id"] = result.correlation_id
    if result.deadline is not None:
        out["deadline"] = result.deadline.isoformat()
    return out


@server.tool(
    description=(
        "Send a message to another task of your request (see get_task_context). To answer "
        "a question you were asked, pass its correlation ID as reply_to."
    )
)
async def send_to_agent(task_id: str, text: str, reply_to: str | None = None) -> dict[str, Any]:
    sender = me()
    args = {"task_id": task_id, "text": text, "reply_to": reply_to}
    try:
        result = await MessageRepository(engine()).send(
            sender, task_id, text, key=_key(sender, "send_to_agent", args), reply_to=reply_to
        )
    except FenceRejected as e:
        raise ToolError("this attempt was superseded; it can no longer send") from e
    return _result(result)


@server.tool(
    description=(
        "Ask another task of your request a question and get its correlation ID. Then call "
        'finish_task with status "waiting"; you are woken with the answer, or told that none '
        "came by the deadline (deadline_seconds, default 300)."
    )
)
async def ask_agent(task_id: str, text: str, deadline_seconds: int | None = None) -> dict[str, Any]:
    sender = me()
    wait = timedelta(seconds=deadline_seconds or DEFAULT_WAIT_S)
    max_wait = timedelta(seconds=float(os.environ.get("PRAXIS_MAX_ASK_WAIT", "600")))
    args = {"task_id": task_id, "text": text, "deadline_seconds": deadline_seconds}
    try:
        result = await MessageRepository(engine()).ask(
            sender, task_id, text, key=_key(sender, "ask_agent", args), wait=wait, max_wait=max_wait
        )
    except FenceRejected as e:
        raise ToolError("this attempt was superseded; it can no longer ask") from e
    return {**_result(result), "next": WAIT_INSTRUCTION}


@server.tool(
    description=(
        "Report your progress: a stage (planning, working, waiting, reviewing, done) and an "
        "optional percentage from 0 to 100. Observers see it as a status event."
    )
)
def post_status(stage: Stage, progress: int | None = None) -> dict[str, Any]:
    if progress is not None and not 0 <= progress <= 100:
        raise ToolError("progress must be between 0 and 100")
    # The runner publishes these validated values as a status event (D15); this
    # server publishes nothing, so each attempt keeps one event producer.
    return {"stage": stage, "progress": progress}


@server.tool(
    description=(
        "Return your task ID, the tasks of your request (IDs, profiles, statuses) and the "
        "messages you sent that their recipients never read."
    )
)
async def get_task_context() -> dict[str, Any]:
    sender = me()
    context = await MessageRepository(engine()).context(sender.task_id)
    return {
        "you": sender.task_id,
        "request_id": context.request_id,
        "tasks": context.tasks,
        "undelivered": context.undelivered,
    }
