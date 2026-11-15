"""Trusted completion adapter for the isolated DSH Activity, using real schemas."""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import asdict
from pathlib import Path

from agents import set_tracing_disabled
from agents.tool_context import ToolContext
from recovery_boundary import Refused

from common.schemas import TurnOutcome
from harness_activity.tools import TurnState, build_tools


class InvalidCompletion(ValueError):
    """finish_task ran but its arguments failed validation: an admitted entry
    with an error outcome, not a policy denial."""


class Completion:
    def __init__(self, workspace: Path):
        set_tracing_disabled(True)
        self.state = TurnState()
        # Only finish_task is invoked here. File/command bodies run in Docker.
        self.tool = next(
            t for t in build_tools(workspace, [], self.state) if t.name == "finish_task"
        )
        self.finished = threading.Event()
        self.lock = threading.Lock()

    def catalog(self) -> list[dict]:
        return [
            {
                "name": self.tool.name,
                "description": self.tool.description,
                "inputSchema": self.tool.params_json_schema,
            }
        ]

    def dispatch(self, name: str, arguments: dict) -> dict:
        with self.lock:
            if name != "finish_task" or self.finished.is_set():
                raise Refused("completion already recorded or tool not granted")
            # Enforce the advertised extra-field policy before invoking the real
            # tool wrapper; model-supplied artifacts never become trusted refs.
            if set(arguments) - set(self.tool.params_json_schema["properties"]):
                raise InvalidCompletion("unknown completion fields")
            payload = json.dumps(arguments)
            context = ToolContext(
                context=None,
                tool_name="finish_task",
                tool_call_id="spike-finish",
                tool_arguments=payload,
            )
            asyncio.run(self.tool.on_invoke_tool(context, payload))
            if self.state.finish is None:
                raise InvalidCompletion("completion arguments failed existing tool validation")
            self.finished.set()
            return {"recorded": True, "status": self.state.finish.status}

    def report(self) -> dict | None:
        with self.lock:
            return asdict(self.state.finish) if self.state.finish is not None else None


def turn_outcome(
    completion: dict | None,
    totals: dict,
    *,
    checkpoint: str,
    tool_calls: int,
    outputs: list,
    error: str | None = None,
) -> TurnOutcome:
    if totals["unknown_usage"]:
        raise RuntimeError("unresolved physical usage cannot be published as zero")
    status = completion["status"] if completion is not None else "continue"
    return TurnOutcome(
        status=status,
        checkpoint_id=checkpoint,
        tokens_in=totals["input_tokens"],
        tokens_out=totals["output_tokens"],
        inner_turns=totals["logical_steps"],
        tool_calls=tool_calls,
        summary=completion["summary"] if completion else "",
        questions=completion["questions"] if completion else [],
        outputs=outputs if status == "done" else [],
        error=error,
    )
