"""Hello-world Workflow for the Phase 0 smoke and replay tests.

Kept free of I/O and non-deterministic calls so it runs in Temporal's sandbox
and replays from tests/fixtures/hello_history.json.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import activity, workflow


@activity.defn
async def say_hello(name: str) -> str:
    return f"Hello, {name}!"


@workflow.defn
class HelloWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        return await workflow.execute_activity(
            say_hello, name, start_to_close_timeout=timedelta(seconds=10)
        )
