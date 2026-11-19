"""Read-only probes for the Phase 2 messaging demo (infra/demo/phase-2-messaging.sh).

    uv run --env-file infra/.env python infra/demo/messaging_probe.py sleeping TASK
    uv run --env-file infra/.env python infra/demo/messaging_probe.py messages TASK...
    uv run --env-file infra/.env python infra/demo/messaging_probe.py history TASK...
    uv run --env-file infra/.env python infra/demo/messaging_probe.py batches TASK
    uv run --env-file infra/.env python infra/demo/messaging_probe.py cancel TASK

`sleeping` prints yes or no; `messages` prints the message rows sent by or to the
tasks; `history` prints each run of each task's Workflow with its event count and
history size; `batches` prints the task's stored events and the batches they came
in; `cancel` cancels the task's Workflow (the demo's cleanup).
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from sqlalchemy import text
from temporalio.api.enums.v1 import EventType

from common.persistence.repositories import make_engine
from workers.main import connect


async def rows(sql: str, **params: Any) -> list[Any]:
    engine = make_engine()
    try:
        async with engine.connect() as conn:
            return list((await conn.execute(text(sql), params)).all())
    finally:
        await engine.dispose()


async def sleeping(task: str) -> None:
    found = await rows("SELECT sleeping FROM task_inbox WHERE task_id = :t", t=task)
    print("yes" if found and found[0][0] else "no")


async def messages(tasks: list[str]) -> None:
    for r in await rows(
        "SELECT created_at, kind, sender_task, recipient_task, status, reason, "
        "left(body, 60) FROM task_messages WHERE sender_task = ANY(:t) OR "
        "recipient_task = ANY(:t) ORDER BY created_at",
        t=tasks,
    ):
        when, kind, sender, recipient, status, reason, body = r
        print(f"{when:%H:%M:%S} {kind:5} {sender} -> {recipient} {status:11} "
              f"{reason or '-'} | {body}")  # fmt: skip


async def history(tasks: list[str]) -> None:
    client = await connect("praxis-demo")
    for task in tasks:
        handle = client.get_workflow_handle(task)
        run = (await handle.describe()).raw_description.workflow_execution_info.first_run_id
        n = 0
        while run:
            events = (await client.get_workflow_handle(task, run_id=run).fetch_history()).events
            size = sum(e.ByteSize() for e in events)
            n += 1
            print(f"{task} run {n} {run}: {len(events)} events, {size} bytes")
            last = events[-1]
            run = (
                last.workflow_execution_continued_as_new_event_attributes.new_execution_run_id
                if last.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CONTINUED_AS_NEW
                else ""
            )


async def batches(task: str) -> None:
    (stored,) = await rows("SELECT count(*) FROM agent_events WHERE workflow_id = :t", t=task)
    # Batch IDs are kept for 600 s (ADR-0009), so run this soon after the task.
    (seen,) = await rows("SELECT count(*) FROM event_batches WHERE workflow_id = :t", t=task)
    print(f"{task}: {stored[0]} events stored in {seen[0]} batches")


async def cancel(task: str) -> None:
    client = await connect("praxis-demo")
    await client.get_workflow_handle(task).cancel()
    print(f"cancelled {task}")


def main(argv: list[str]) -> None:
    command, args = argv[0], argv[1:]
    if command == "sleeping":
        asyncio.run(sleeping(args[0]))
    elif command == "messages":
        asyncio.run(messages(args))
    elif command == "history":
        asyncio.run(history(args))
    elif command == "batches":
        asyncio.run(batches(args[0]))
    elif command == "cancel":
        asyncio.run(cancel(args[0]))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
